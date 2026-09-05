"""
SAM — Personal AI Assistant
Self-learning Autonomous Mind with Hermes Intelligence & Taste Heuristics Architecture

Entry point. Supports both voice and text input modes.
Start in voice mode: python main.py
Start in text mode:  python main.py --text
"""

import sys
import signal
import logging
import argparse
import threading
from dataclasses import replace
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.FileHandler("logs/sam.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SAM")

from config.settings import Settings, validate_assistant_name
from ears.wake_word import WakeWordListener
from ears.text_input import TextInputListener
from ears.stt import SpeechToText
from core.brain import Brain
from core.session import Session
from mouth.tts import TextToSpeech
from memory.identity import Identity
from memory.retrieve import MemoryRetriever
from founder_mode.manager import FounderModeManager
from agent.react_loop import ReactLoop


def run_task_with_optional_sovereign_mode(
    react_loop, settings, task, brain, session, founder_context, initial_response, cancel_event,
    on_step=None,
):
    """
    Milestone 6 — the actual Sovereign integration point.

    Runs the real ReAct task via react_loop.run_planned_task(), optionally
    wrapped in SocketGuard when settings.sovereign_mode is True. Returns
    (result_text, network_report) — network_report is None when Sovereign
    Mode didn't run (the default), so callers can tell the difference
    between "not measured" and "measured, and it was clean."

    Extracted as a standalone module-level function — not a SAM method —
    so it's testable directly (real ReactLoop, real SocketGuard, mocked
    only where Brain/Planner genuinely need a live Ollama) without
    constructing a full SAM instance, which needs audio hardware this
    sandbox doesn't have. SAM._run_task below is a thin wrapper around
    this for _process() to call.

    on_step: M8-A — optional callback(step_dict), passed straight through
    to react_loop.run_planned_task() unchanged. Omit for old behaviour.
    """
    if not settings.sovereign_mode:
        result_text = react_loop.run_planned_task(
            task=task, brain=brain, session=session, founder_context=founder_context,
            initial_response=initial_response, cancel_event=cancel_event, on_step=on_step,
        )
        return result_text, None

    from sovereign.security import SocketGuard, write_evidence_log

    guard = SocketGuard(settings, task_label=task[:80])
    try:
        with guard:
            result_text = react_loop.run_planned_task(
                task=task, brain=brain, session=session, founder_context=founder_context,
                initial_response=initial_response, cancel_event=cancel_event, on_step=on_step,
            )
        return result_text, guard.report()
    finally:
        # Evidence is written even on failure — a task that errored out
        # while guarded is exactly the case you most want a record of,
        # not less of one. guard.report() is safe to call here whether
        # the `with` block above exited normally or via exception —
        # SocketGuard.__exit__ always sets ended_at before returning.
        report = guard.report()
        write_evidence_log(report, settings)
        logger.info(
            f"Sovereign task evidence — blocked={report.blocked_count}, "
            f"external={report.external_transmission_count}, "
            f"log={settings.sovereign_network_log}"
        )


class SAM:
    def __init__(self, start_in_text_mode: bool = False):
        logger.info("SAM initialising...")
        self.settings = Settings()

        # M6.2 — Identity.assistant_name (memory/identity.py) is the
        # single persistent source of truth for the display name; see
        # config/settings.py's comment on why it isn't a Settings field.
        # First-run detection: a file that didn't exist before this
        # process touched it is unambiguously fresh. A pre-existing file
        # is only "incomplete" if it explicitly says so via
        # setup_completed=False (written below, right after a fresh
        # file is created) — a pre-existing file with NO such key at all
        # predates this feature and must be left alone, not re-prompted.
        identity_existed_before = Identity.path().exists()
        self.identity = Identity()
        if not identity_existed_before:
            self.identity.update({"setup_completed": False})
        current_identity = self.identity.load()
        self._is_first_run = current_identity.get("setup_completed") is False
        self._display_name = current_identity.get("assistant_name", "VEDA")  # short-lived cache — always re-synced from Identity after any change
        self._name_overridden_via_cli = False

        self.memory = MemoryRetriever()
        self.founder_mode = FounderModeManager(settings=self.settings)
        self.brain = Brain(self.settings)
        self.react_loop = ReactLoop(self.settings, founder_mode=self.founder_mode)
        self.tts = TextToSpeech(self.settings)
        self.stt = SpeechToText(self.settings)
        self.wake_word = WakeWordListener(self.settings, callback=self.on_wake_voice)
        self.text_input = TextInputListener(
            callback=self.on_text_input,
            mode_switch_callback=self.switch_mode
        )
        self._running = False
        self._input_mode = "text" if start_in_text_mode else "voice"
        # Concurrency fix (found via real Mac testing): text_input.py and
        # wake_word.py both fire an unsynchronized new thread per trigger.
        # Without this lock, a second message arriving while the first was
        # still processing (10-30+ seconds is normal) ran CONCURRENTLY on a
        # separate thread, touching the same shared, NOT thread-safe state
        # -- the cached Playwright Page in particular, whose sync API is
        # bound to whichever thread created it. That's the exact mechanism
        # behind the real "cannot switch to a different thread (which
        # happens to have exited)" crash seen in testing, and also why
        # typing "stop it" during a running task didn't stop anything -- it
        # just started running concurrently instead of queuing after it.
        # This lock is the single chokepoint both text and voice input
        # converge on, so one lock here covers both input sources.
        self._process_lock = threading.Lock()
        # Interrupt/Stop: a thread-safe signal the CURRENTLY RUNNING task
        # checks between steps. This is the real fix for the "stop it"
        # bug seen in real testing — typing "stop it" while a task ran
        # just queued behind self._process_lock and never actually
        # interrupted anything. Setting an Event is instant regardless of
        # whether the lock is held, so cancellation requests are intercepted
        # in _process() BEFORE the lock is ever touched — see below.
        self._cancel_event = threading.Event()
        self._STOP_PHRASES = {"stop", "stop it", "cancel", "cancel that", "abort", "never mind", "nevermind"}

    # ─── Input Handlers ───────────────────────────────────────────────────

    def on_wake_voice(self):
        """Called by wake word listener — records and transcribes speech."""
        logger.info("Wake word detected — recording...")
        user_input = self.stt.listen()
        if user_input and user_input.strip():
            self._process(user_input)

    def on_text_input(self, text: str):
        """Called by text input listener — processes typed input directly."""
        logger.info(f"Text input: {text}")
        self._process(text)

    # ─── Core Processing ──────────────────────────────────────────────────

    def _process(self, user_input: str):
        """Shared processing pipeline for both voice and text input.
        Serialized via self._process_lock -- see __init__ for why."""
        normalized = user_input.strip().lower()
        if normalized in self._STOP_PHRASES:
            was_running = self._process_lock.locked()
            self._cancel_event.set()
            msg = ("Stopping now." if was_running
                   else "Nothing's running right now, but noted.")
            print(f"\n{self._display_name}: {msg}\n")
            if self.settings.tts_engine != "none":
                self.tts.speak(msg)
            return

        acquired = self._process_lock.acquire(blocking=False)
        if not acquired:
            print(f"\n[{self._display_name}] Still working on your previous request — "
                  "this will run right after it finishes.\n")
            self._process_lock.acquire()  # now wait our turn

        try:
            # Handle built-in commands first
            if self._handle_command(user_input):
                return

            # Build session context
            session = Session(
                user_input=user_input,
                identity=self.identity.load(),
                memories=self.memory.retrieve(user_input, self.settings,
                                               retention_days=self._memory_retention_days()),
                founder_context=self.founder_mode.get_context(),
                settings=self.settings
            )

            # Get response from Brain
            response = self.brain.process(session)
            logger.info(f"Brain response — action: {response.action}")

            final_response = response

            # If the Brain decided an action is needed, ACTUALLY execute it.
            # Before this change, main.py only ever spoke response.text —
            # which is the Brain's pre-action claim ("Opening YouTube...")
            # written in the same breath as deciding the action, not a
            # report of anything that happened. Nothing downstream of that
            # ever ran. Now: run the task for real through the ReAct loop
            # (Planner-first, verified with 1 retry, falls back to the
            # adaptive loop if planning fails), and speak/save the loop's
            # actual result instead of the pre-action guess.
            if response.action and response.action not in (None, "none"):
                try:
                    self._cancel_event.clear()  # fresh start — don't inherit a stale cancel from a prior interrupted task
                    real_result_text, network_report = self._run_task(user_input, session, response)
                    final_response = replace(response, text=real_result_text)
                except Exception as e:
                    logger.error(f"Task execution failed: {e}", exc_info=True)
                    final_response = replace(
                        response,
                        text=f"I tried to do that but hit an error: {e}"
                    )

            logger.info(f"SAM: {final_response.text}")

            # Always print response — useful in text mode
            print(f"\n{self._display_name}: {final_response.text}\n")

            # Speak response (unless in silent/text-only mode)
            if self.settings.tts_engine != "none":
                self.tts.speak(final_response.text)

            # Save session to memory — records what actually happened,
            # not the discarded pre-action claim
            if not self.settings.incognito:
                session.save(user_input=user_input, response=final_response,
                             memory_store=self.memory.get_store(self.settings))

            # Founder Mode capture — same, sees the real outcome
            self.founder_mode.capture_if_relevant(user_input, final_response)

        except Exception as e:
            logger.error(f"Processing error: {e}", exc_info=True)
            error_msg = "I hit an error. Check the logs."
            print(f"\n{self._display_name}: {error_msg}\n")
            if self.settings.tts_engine != "none":
                self.tts.speak(error_msg)
        finally:
            self._process_lock.release()

    # ─── Commands ─────────────────────────────────────────────────────────

    def _run_task(self, user_input: str, session: Session, response):
        """Thin wrapper — see run_task_with_optional_sovereign_mode above
        for the actual Sovereign integration logic."""
        return run_task_with_optional_sovereign_mode(
            self.react_loop, self.settings, user_input, self.brain, session,
            session.founder_context, response, self._cancel_event,
        )

    def _memory_retention_days(self):
        """Free tier: 7-day memory cap. Pro tier / enforcement off: None
        (unlimited), unchanged from before tier-gating existed."""
        from licensing.tier import get_tier, PRO, FREE_TIER_MEMORY_RETENTION_DAYS
        return None if get_tier(self.settings) == PRO else FREE_TIER_MEMORY_RETENTION_DAYS

    def _handle_command(self, text: str) -> bool:
        """Handle built-in SAM commands. Returns True if handled."""
        t = text.lower().strip()

        # Mode switching
        if any(p in t for p in ["text mode", "switch to text", "type mode", "silent mode"]):
            self.switch_mode("text")
            return True

        if any(p in t for p in ["voice mode", "switch to voice", "speak mode"]):
            self.switch_mode("voice")
            return True

        # Incognito (Pro tier — per the frozen pricing table)
        if "incognito" in t and "exit" not in t and "leave" not in t:
            from licensing.tier import get_tier, PRO
            if get_tier(self.settings) != PRO:
                msg = "Incognito mode is a Pro feature. Activate a license to use it."
                print(f"\n{self._display_name}: {msg}\n")
                self.tts.speak(msg)
                return True
            self.settings.incognito = True
            msg = "Incognito mode on. Nothing will be recorded."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            return True

        if any(p in t for p in ["exit incognito", "leave incognito"]):
            self.settings.incognito = False
            msg = "Incognito off. Memory is back on."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            return True

        # Sovereign Mode (Milestone 6, SIH26117) — real task execution runs
        # inside SocketGuard; not a licensed feature, just explicit opt-in.
        if "sovereign mode" in t and "off" not in t and "exit" not in t and "leave" not in t:
            self.settings.sovereign_mode = True
            msg = "Sovereign mode on. Task execution will run inside the network guard."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            return True

        if any(p in t for p in ["sovereign mode off", "exit sovereign", "leave sovereign"]):
            self.settings.sovereign_mode = False
            msg = "Sovereign mode off."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            return True

        # Runtime display identity (M6.2, SIH26117) — matched by exact
        # phrase / prefix, not loose substring: "name" alone is too
        # common a word to safely match anywhere in a normal sentence.
        # Persists through Identity.update() — the same mechanism a
        # first-run naming choice uses — so it survives a restart.
        if t in ("name", "what is your name", "what's your name"):
            msg = f"My name is {self._display_name}."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            return True

        if t.startswith("name ") and len(t) > len("name "):
            requested = text.strip()[len("name "):].strip()
            try:
                new_name = validate_assistant_name(requested)
                self._display_name = new_name
                self.identity.update({"assistant_name": new_name})
                msg = f"Alright, call me {new_name} from now on."
                print(f"\n{new_name}: {msg}\n")
                self.tts.speak(msg)
            except ValueError as e:
                msg = f"That name doesn't work: {e}"
                print(f"\n{self._display_name}: {msg}\n")
                self.tts.speak(msg)
            return True

        # Local model selection. Only installed Ollama models are accepted
        # when Ollama is reachable; an offline choice is retained so SAM can
        # be configured before its local service is started.
        if t.startswith("model ") and len(t) > len("model "):
            requested = text.strip()[len("model "):].strip()
            try:
                models = self.brain.list_installed_models()
                if models and requested not in models:
                    msg = f"{requested} is not installed. Available models: {', '.join(models)}."
                    print(f"\n{self._display_name}: {msg}\n")
                    self.tts.speak(msg)
                    return True
            except RuntimeError:
                # Keep the chosen local model; it will be verified when SAM
                # next reaches the local Ollama service.
                pass

            self.settings.primary_model = requested
            self.settings.model_explicitly_set = True
            self.settings.save()
            msg = f"I'll use {requested}."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            return True

        # Sleep / Stop
        if any(p in t for p in ["sam sleep", "go to sleep"]):
            msg = "Going to sleep. Call me when you need me."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            self.brain.unload()
            return True

        if any(p in t for p in ["sam stop", "shut down", "goodbye sam", "quit"]):
            msg = "Shutting down. Goodbye."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            self.stop()
            return True

        return False

    # ─── Mode Switching ───────────────────────────────────────────────────

    def switch_mode(self, mode: str):
        """Switch between voice and text input modes at runtime."""
        if mode == "text":
            self._input_mode = "text"
            self.wake_word.stop()
            msg = "Switched to text mode. Type your messages."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            self.text_input.start()
            self.text_input.join()

        elif mode == "voice":
            self._input_mode = "voice"
            self.text_input.stop()
            msg = "Switched to voice mode. Say Hey SAM."
            print(f"\n{self._display_name}: {msg}\n")
            self.tts.speak(msg)
            self.wake_word.start()

    # ─── Lifecycle ────────────────────────────────────────────────────────

    def _run_first_run_setup(self):
        """First run only: choose the display name, then select from models
        that Ollama actually reports as installed. SAM never pulls models
        automatically and still starts in a useful degraded mode when no
        local model service is available."""
        print(f"\nWelcome. Let's get set up.\n")

        print("STEP 1 — Name your assistant")
        if self._name_overridden_via_cli:
            chosen = self._display_name
            print(f"Using the name from --name: {chosen}")
        else:
            raw = input(f"What would you like to call me? [{self._display_name}]: ").strip()
            if raw:
                try:
                    chosen = validate_assistant_name(raw)
                except ValueError as e:
                    print(f"({e} — keeping {self._display_name})")
                    chosen = self._display_name
            else:
                chosen = self._display_name  # accepted the default
        self._display_name = chosen
        print(f"Got it — I'll go by {chosen}.\n")

        print("STEP 2 — Checking your local model setup")
        try:
            models = self.brain.list_installed_models()
            if not models:
                raise RuntimeError("No local models are installed in Ollama.")

            default = self.settings.primary_model if self.settings.primary_model in models else models[0]
            print(f"Available local models: {', '.join(models)}")
            raw_model = input(f"Choose a primary model [{default}]: ").strip()
            selected = raw_model or default
            valid_selection = selected in models
            if not valid_selection:
                print(f"{selected} is not installed — using {default}.")
                selected = default

            self.settings.primary_model = selected
            self.settings.model_explicitly_set = True
            fallback_candidates = [model for model in models if model != selected]
            if valid_selection and fallback_candidates:
                raw_fallback = input(
                    f"Optional fallback model [{self.settings.fallback_model}] "
                    "(or 'skip'): "
                ).strip()
                if raw_fallback and raw_fallback.lower() != "skip":
                    if raw_fallback in models:
                        self.settings.fallback_model = raw_fallback
                    else:
                        print(f"{raw_fallback} is not installed — fallback unchanged.")
            self.settings.save()
            print(f"Model check: using {selected}.\n")
        except RuntimeError as e:
            print(f"Model check: {e}")
            print(f"({chosen} will still start — you'll just need that "
                  f"sorted before {chosen} can actually respond.)\n")

        self.identity.update({"assistant_name": chosen, "setup_completed": True})
        self._is_first_run = False
        print("Setup complete.\n")

    def start(self):
        self._running = True

        if self._is_first_run:
            self._run_first_run_setup()

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        # Phase 3: non-blocking license check. Per the frozen principle
        # ("no hard license enforcement at launch — non-blocking warnings
        # only"), this NEVER stops SAM from starting, even if unlicensed,
        # expired, or invalid. It only logs/prints a notice. Flip
        # settings.license_enforcement_enabled if you deliberately want
        # enforcement later — this code path doesn't check that flag
        # itself (enforcement logic, if ever added, is a separate,
        # explicit decision from this notice).
        try:
            from licensing.license_manager import LicenseManager, LicenseStatus
            status, message, lic = LicenseManager().check()
            if status == LicenseStatus.VALID:
                logger.info(f"License: {lic.product_edition} ({message})")
            elif status == LicenseStatus.NO_LICENSE:
                logger.info("Running unlicensed (non-blocking) — "
                             "activate with: python sam_cli.py activate <file>")
            else:
                logger.warning(f"License check: {status} — {message} (non-blocking, SAM continues normally)")
        except Exception as e:
            logger.debug(f"License check skipped due to an internal error (non-blocking): {e}")

        ready_msg = f"{self._display_name} is ready."
        print(f"\n{self._display_name}: {ready_msg}\n")
        self.tts.speak(ready_msg)

        if self._input_mode == "text":
            logger.info("Starting in TEXT mode")
            self.text_input.start()
            self.text_input.join()
        else:
            logger.info("Starting in VOICE mode")
            # "Hey SAM" stays literal — it's the actual trained wake
            # phrase for the (untouched) wake-word engine, not a display
            # string. Only the heading uses the configured display name.
            print(f"\n{self._display_name} VOICE MODE — Say 'Hey SAM' to activate")
            print("Say 'text mode' anytime to switch to typing\n")
            self.wake_word.start()  # Blocking

    def stop(self):
        self._running = False
        self.wake_word.stop()
        self.text_input.stop()
        logger.info("SAM stopped.")
        sys.exit(0)

    def _shutdown(self, sig, frame):
        logger.info("Shutdown signal received")
        self.stop()


def _build_arg_parser() -> argparse.ArgumentParser:
    """Extracted from the __main__ block so --name (and the rest of the
    CLI surface) is testable without running the full interactive loop."""
    parser = argparse.ArgumentParser(description="SAM — Personal AI Assistant")
    parser.add_argument(
        "--text",
        action="store_true",
        help="Start in text input mode (no microphone needed)"
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Disable TTS — print responses only"
    )
    parser.add_argument(
        "--sovereign",
        action="store_true",
        help="Start in Sovereign Mode — task execution runs inside the network guard (SIH26117)"
    )
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help=("Temporarily override the assistant's display name for this run only "
              "(default comes from the persisted identity, VEDA on first run). "
              "Does not save — use the runtime 'name X' command to change it permanently.")
    )
    return parser


if __name__ == "__main__":
    parser = _build_arg_parser()
    args = parser.parse_args()

    sam = SAM(start_in_text_mode=args.text)

    if args.silent:
        sam.settings.tts_engine = "none"
    if args.sovereign:
        sam.settings.sovereign_mode = True
    if args.name:
        try:
            sam._display_name = validate_assistant_name(args.name)
            sam._name_overridden_via_cli = True
        except ValueError as e:
            print(f"Invalid --name: {e}")
            sys.exit(1)

    sam.start()
