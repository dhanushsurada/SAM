"""
AGENT — ReAct Loop
Reason → Act → Observe → Repeat until task complete.
Routes Brain decisions to the correct Hand.
"""

import time
import logging
import json
from typing import Optional, Dict, Any

from agent import planner
from agent.reflection import ReflectionEngine
from agent.verifier import Verifier

logger = logging.getLogger("SAM.Agent")

MAX_STEPS = 10  # Safety limit on autonomous steps
STAGNATION_WINDOW = 3  # Abort early if this many consecutive observations are identical
CLICK_RECHECK_TOLERANCE_PX = 40  # Phase 1: how close a re-found target has to be to its
# pre-click location to count as "still sitting right there" (see _execute_control's
# click branch) rather than "vision found something else nearby after the screen changed"
OPEN_APP_POLL_INTERVAL_S = 0.3  # Phase 1: how often to re-check get_frontmost_app() after
OPEN_APP_POLL_TIMEOUT_S = 1.8   # open_app() -- an already-running app typically becomes
# frontmost almost immediately (first check, no extra wait); these numbers give a
# cold-launching app a bit of room without stalling every open_app call. Untested against
# a real cold launch on real hardware -- tune if 1.8s proves too short (or needlessly long).

# Phase 2 (task lifecycle): the honest-outcome vocabulary run_task()/run_planned_task()
# report via TaskOutcome.status below. Deliberately reuses MAX_STEPS and STAGNATION_WINDOW
# as the bounds that decide between these, rather than introducing a separate "retry
# budget" constant -- those are the existing abstractions that already bound a task.
STATUS_SUCCESS = "success"                        # finished, and nothing along the way
# was left unresolved after its retry.
STATUS_FAILED = "failed"                          # finished (Brain said done, or the plan
# ran to its end), but at least one action never verified as successful even after retry.
STATUS_STOPPED_AFTER_RETRIES = "stopped_after_retries"  # stopped early: repetition
# detected (identical observations, or the identical action failing repeatedly) before
# reaching a natural end.
STATUS_UNABLE_TO_VERIFY = "unable_to_verify"      # hit MAX_STEPS without reaching either
# a clean success or a clear stuck-repetition signal -- genuinely ambiguous.
STATUS_CANCELLED = "cancelled"                    # the caller's cancel_event fired.


class TaskOutcome(str):
    """
    The text result of run_task()/run_planned_task(), exactly as before --
    behaves as a plain str in every way (equality, formatting, slicing,
    concatenation, `in`, sqlite3/json/dataclass field assignment, all of
    it -- verified directly, not assumed) so every existing caller and
    test that treats the return value as a string keeps working
    unchanged. The one addition is `.status`, one of the STATUS_*
    constants above, for callers that want the honest
    success/failed/stopped_after_retries/unable_to_verify/cancelled
    distinction without parsing the prose. Any *derived* string (e.g.
    result.lower()) reverts to a plain str per normal Python str
    semantics -- only the direct return value itself carries `.status`.
    """
    def __new__(cls, text: str, status: str):
        obj = super().__new__(cls, text)
        obj.status = status
        return obj


class ReactLoop:
    def __init__(self, settings, founder_mode=None):
        self.settings = settings
        self._control = None
        self._browser = None
        self._terminal = None
        self._vision = None
        self._reflection = ReflectionEngine(settings)
        self._verifier = Verifier(settings)
        # Optional — pass a FounderModeManager to let high-confidence
        # reflections bridge into Founder Mode. Omit to keep old behaviour.
        self.founder_mode = founder_mode

    def _get_control(self):
        if self._control is None:
            from hands.control.controller import ComputerController
            self._control = ComputerController()
        return self._control

    def _get_browser(self):
        if self._browser is None:
            from hands.browser.playwright_agent import BrowserAgent
            self._browser = BrowserAgent()
        return self._browser

    def _get_terminal(self):
        if self._terminal is None:
            from hands.terminal.runner import TerminalRunner
            allow_risky = getattr(self.settings, "allow_risky_terminal_commands", False)
            self._terminal = TerminalRunner(allow_risky=allow_risky)
        return self._terminal

    def _get_vision(self):
        if self._vision is None:
            from hands.vision.screen_reader import ScreenReader
            self._vision = ScreenReader(self.settings)
        return self._vision

    def execute(self, action: str, payload: Dict[str, Any]) -> str:
        """
        Execute a single action and return the observation.
        """
        logger.info(f"Executing action: {action} | payload: {payload}")

        try:
            if action == "control":
                return self._execute_control(payload)
            elif action == "browser":
                return self._execute_browser(payload)
            elif action == "terminal":
                return self._execute_terminal(payload)
            elif action == "vision":
                return self._execute_vision(payload)
            else:
                return f"Unknown action: {action}"

        except Exception as e:
            logger.error(f"Action execution error: {e}", exc_info=True)
            return f"Error executing {action}: {str(e)}"

    def _execute_verified(self, action: str, payload: Dict[str, Any], step_label: str) -> Dict:
        """
        Phase 1.5: executes an action, verifies the result, and retries
        ONCE on failure (same action, same payload — no auto-repair).
        Both attempts are always logged, and both are always included in
        what gets passed to Reflection, whether the final outcome is a
        success (after retry) or an abort (failed twice).
        """
        attempts = []

        start = time.time()
        observation = self.execute(action, payload)
        elapsed = time.time() - start
        result = self._verifier.verify(action, payload, observation, elapsed)
        attempts.append({
            "attempt": 1, "observation": observation,
            "success": result.success, "confidence": result.confidence,
            "errors": result.errors, "execution_time": elapsed,
        })
        decision = self._verifier.decide(result, already_retried=False)
        logger.info(f"[{step_label}] attempt 1: {'OK' if result.success else 'FAILED'} (decision={decision})")

        final_observation = observation
        final_success = result.success

        if decision == "retry":
            start = time.time()
            observation2 = self.execute(action, payload)
            elapsed2 = time.time() - start
            result2 = self._verifier.verify(action, payload, observation2, elapsed2)
            attempts.append({
                "attempt": 2, "observation": observation2,
                "success": result2.success, "confidence": result2.confidence,
                "errors": result2.errors, "execution_time": elapsed2,
            })
            final_decision = self._verifier.decide(result2, already_retried=True)
            logger.info(f"[{step_label}] attempt 2 (retry): {'OK' if result2.success else 'FAILED'} "
                        f"(decision={final_decision})")
            final_observation = observation2
            final_success = result2.success

        return {"observation": final_observation, "success": final_success, "attempts": attempts}

    # Latency fix #4: cheap keyword pre-filter so single-action requests
    # ("open youtube", "what's the weather") skip the Planner's separate
    # LLM call entirely, instead of every action paying for a planning
    # round-trip it doesn't need. High recall on purpose — a false
    # positive just means an unnecessary (but harmless) plan; a false
    # negative means a genuinely multi-step task gets planned anyway
    # since run_task's own adaptive loop still handles it correctly,
    # just without the upfront plan.
    _MULTI_STEP_SIGNALS = [
        " then ", " after that", " after ", " and then", " next,",
        " next ", ", then", "; then", " followed by", " once done",
        " once that", " first,", " first ", " finally "
    ]

    def _looks_multi_step(self, task: str) -> bool:
        t = f" {task.lower()} "
        return any(sig in t for sig in self._MULTI_STEP_SIGNALS)

    @staticmethod
    def _same_spot(a: tuple, b: tuple) -> bool:
        """True if two (x, y) pixel points are within
        CLICK_RECHECK_TOLERANCE_PX of each other — used to tell "the same
        element is still sitting right there" from "vision found
        something else, some distance away, after the screen changed"."""
        return (abs(a[0] - b[0]) <= CLICK_RECHECK_TOLERANCE_PX
                and abs(a[1] - b[1]) <= CLICK_RECHECK_TOLERANCE_PX)

    @staticmethod
    def _same_app(requested: str, frontmost: str) -> bool:
        """
        Loose match between the app name the Brain asked to open and
        what's actually frontmost. Real display names vary a lot for the
        same app -- "VS Code" / "Visual Studio Code" / "Code" are all the
        same application, and neither "VS Code" nor "Visual Studio Code"
        is a substring of the other, so a pure substring check misses
        exactly the app from the original bug report. Matches if either
        string contains the other (handles "Chrome" / "Google Chrome"),
        OR if they share their last word (handles "VS Code" / "Visual
        Studio Code", since both end in "code"). Still a heuristic --
        e.g. two unrelated apps that happen to share a generic last word
        would false-match -- but it covers the common real cases without
        a hand-maintained name-alias table.
        """
        a, b = requested.strip().lower(), frontmost.strip().lower()
        if not a or not b:
            return False
        if a in b or b in a:
            return True
        a_words, b_words = a.split(), b.split()
        return bool(a_words) and bool(b_words) and a_words[-1] == b_words[-1]

    def _poll_for_frontmost_match(self, controller, app: str):
        """
        Polls get_frontmost_app() for up to OPEN_APP_POLL_TIMEOUT_S,
        returning as soon as the frontmost app matches `app` (_same_app)
        instead of checking exactly once, right after issuing the
        activate command -- macOS can take a moment to bring a
        cold-launched app to the foreground.

        Returns (matched: bool, last_seen: str | None). last_seen is
        None only if get_frontmost_app() itself never once succeeded
        (e.g. the System Events automation permission isn't granted) --
        that's a different, more fundamental problem than "still
        launching", and is reported as such by the caller.
        """
        deadline = time.monotonic() + OPEN_APP_POLL_TIMEOUT_S
        last_seen = None
        while True:
            try:
                last_seen = controller.get_frontmost_app()
                if last_seen and self._same_app(app, last_seen):
                    return True, last_seen
            except Exception as e:
                logger.debug(f"get_frontmost_app() failed during open_app verification: {e}")
            if time.monotonic() >= deadline:
                return False, last_seen
            time.sleep(OPEN_APP_POLL_INTERVAL_S)

    def _is_stagnant(self, observations: list) -> bool:
        """
        Detects the ReAct loop being stuck repeating the exact same
        observation instead of making progress — e.g. "No content found"
        over and over, seen in real testing burning through all MAX_STEPS
        without ever getting closer to done. Exact string match on
        purpose: fuzzy similarity risks false-aborting on genuinely
        different steps that happen to read similarly, which is worse
        than occasionally missing a near-duplicate.
        """
        if len(observations) < STAGNATION_WINDOW:
            return False
        recent = [o.get("observation", "") for o in observations[-STAGNATION_WINDOW:]]
        return recent[0] != "" and len(set(recent)) == 1

    @staticmethod
    def _action_key(observation: dict):
        """
        A comparable identity for an executed step -- same action type +
        same payload -- used by _is_repeating_failed_action below to
        detect "trying the identical thing repeatedly" independent of how
        the *resulting* observation text happens to read. Returns None
        for a step that wasn't an action (a plain text response, or a
        malformed payload) -- there's nothing meaningful to call
        "repeated" there, so it never counts toward a repeat.
        """
        action = observation.get("action")
        if not action:
            return None
        payload = observation.get("payload")
        if payload is None:
            payload = observation.get("description")
        try:
            return (action, json.dumps(payload, sort_keys=True, default=str))
        except Exception:
            return (action, str(payload))

    def _is_repeating_failed_action(self, observations: list) -> bool:
        """
        Detects choosing the exact same action + payload STAGNATION_WINDOW
        times in a row where *every* one of those attempts failed
        verification. Complements _is_stagnant(): that method compares
        observation *text*, which Phase 1 made descriptive rather than a
        bare repeated self-report (e.g. vision.read()'s free-text
        phrasing can vary slightly between attempts even when the
        underlying problem — and the action chosen in response to it —
        stays exactly the same), so a loop can now be genuinely stuck on
        one action without ever producing three byte-identical
        observations. This is the direct, action-identity signal for
        that case.
        """
        if len(observations) < STAGNATION_WINDOW:
            return False
        recent = observations[-STAGNATION_WINDOW:]
        if any(o.get("success", True) for o in recent):
            return False  # at least one recent attempt verified fine -- not stuck
        keys = {self._action_key(o) for o in recent}
        return len(keys) == 1 and None not in keys

    @staticmethod
    def _last_action_unresolved(observations: list) -> bool:
        """
        True if the most recently *executed* action (skipping any pure
        text steps, which have no attempts) never verified as successful,
        even after its retry. Used at each "the loop finished normally"
        exit point to tell a genuine success from "I reached the end, but
        the last thing I did never worked" — reaching the end of a plan,
        or the Brain saying it's done, doesn't by itself mean the task
        actually succeeded, and previously nothing checked.

        Deliberately checks only the *last* executed action, not "was
        there ever a failure anywhere in the history": an earlier action
        failing and then a later, different action succeeding is a
        recovery, not an unresolved problem (see TEST C in the Phase 2
        brief) — only whether things ended in a working state should
        turn an otherwise-clean finish into a reported failure.
        """
        for o in reversed(observations):
            if o.get("attempts") is not None:
                return not o.get("success", True)
        return False

    def run_task(self, task: str, brain, session, initial_response=None, cancel_event=None,
                 on_event=None) -> TaskOutcome:
        """
        Run a multi-step autonomous task using ReAct loop.
        Continues until task is complete, MAX_STEPS reached, or cancelled.

        Latency fix #1: if initial_response is provided (the caller already
        got a Brain response for this exact task — e.g. main.py's first
        classification call), the first loop iteration reuses it instead of
        calling brain.process() again for the same decision. Every
        iteration after the first still reasons fresh, exactly as before.
        Omit initial_response to get the old behaviour unchanged.

        cancel_event: an optional threading.Event checked between every
        step. This is the actual interrupt mechanism (main.py sets it the
        instant the user says "stop", bypassing the process lock entirely
        so it takes effect even while this loop is mid-execution). Omit it
        to get the old, never-cancellable behaviour unchanged.

        Returns a TaskOutcome (see class docstring) -- a plain str for
        every existing caller, with `.status` for callers that want the
        honest success/failed/stopped_after_retries/unable_to_verify/
        cancelled distinction (Phase 2).
        """
        logger.info(f"Starting ReAct loop for task: {task}")
        observations = []
        steps = 0

        current_input = task
        response = initial_response

        while steps < MAX_STEPS:
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Task cancelled by user request")
                result = "Stopped."
                self._safe_reflect(task, observations, result)
                return TaskOutcome(result, STATUS_CANCELLED)

            steps += 1
            logger.info(f"ReAct step {steps}/{MAX_STEPS}")

            if response is None:
                # Reason: ask brain what to do next
                session.user_input = self._build_react_prompt(task, observations, current_input)
                response = brain.process(session)

            # Check if task is complete
            if response.action is None or response.action == "none":
                logger.info("Task complete — no more actions needed")
                self._safe_reflect(task, observations, response.text)
                status = (STATUS_FAILED if self._last_action_unresolved(observations)
                          else STATUS_SUCCESS)
                return TaskOutcome(response.text, status)

            # Act: execute the action (Phase 1.5: verified, with 1 retry on failure)
            self._safe_event(on_event, "executing", f"Step {steps}: {response.action}")
            verified = self._execute_verified(response.action, response.action_payload or {}, f"step {steps}")
            self._safe_event(on_event, "verifying",
                              f"Step {steps} {'verified' if verified['success'] else 'failed verification'}")
            observation = verified["observation"]
            observations.append({
                "step": steps,
                "action": response.action,
                "payload": response.action_payload,
                "observation": observation,
                "attempts": verified["attempts"],
                "success": verified["success"],
            })
            logger.info(f"Observation: {observation[:100]}")

            current_input = f"Observation from last step: {observation}"
            if not verified["success"]:
                current_input += (
                    "\n\nThat did not verify as successful even after a retry. Do not "
                    "just repeat the same action — re-check what's actually on screen "
                    "and choose a different approach, or say there's nothing more you "
                    "can do if no reasonable alternative exists.")
            response = None  # force fresh reasoning on the next iteration

            if self._is_stagnant(observations) or self._is_repeating_failed_action(observations):
                logger.warning(f"Stagnation detected — stuck repeating without progress "
                                f"{STAGNATION_WINDOW}x in a row, aborting early instead "
                                f"of burning the remaining steps")
                result = (f"I got stuck repeating the same approach without making "
                          f"progress ('{observations[-1]['observation'][:80]}'), so I "
                          f"stopped instead of continuing to retry.")
                self._safe_reflect(task, observations, result)
                return TaskOutcome(result, STATUS_STOPPED_AFTER_RETRIES)

        logger.warning(f"ReAct loop reached max steps ({MAX_STEPS})")
        result = "I ran out of steps before completing the task. Please try again."
        self._safe_reflect(task, observations, result)
        return TaskOutcome(result, STATUS_UNABLE_TO_VERIFY)

    def run_planned_task(self, task: str, brain, session, founder_context: str = "",
                          initial_response=None, cancel_event=None, on_event=None) -> TaskOutcome:
        """
        Phase 1: Plans the task into ordered steps first, then executes
        each step. Falls back to the original adaptive run_task() if
        planning is unavailable, returns nothing, or the task doesn't look
        multi-step to begin with (latency fix #4) — the old loop is
        untouched and remains the default behaviour whenever planning
        doesn't apply.

        Latency fix #1: initial_response (if provided) is reused for the
        FIRST planned step instead of making a fresh Brain call for it —
        the plan's first step is usually the same action the Brain already
        decided on when first asked. Every step after that still reasons
        fresh, exactly as before. This is an approximation, not a
        guarantee the fresh-asked answer would've been identical — but it
        was already just as much a guess before this change, and it saves
        a full LLM round-trip on every single action turn.

        cancel_event: same interrupt mechanism as run_task — checked
        between every planned step, and passed through to run_task on
        either fallback path so cancellation works identically regardless
        of which path a task ends up on.

        on_event: iQOO Phase 1 adapter — optional callback(phase, message)
        fired at plan creation, before/after each step's execution, and on
        stagnation abort. Additive and backward-compatible: default None
        means zero behaviour change for existing callers. See _safe_event.

        Returns a TaskOutcome (see class docstring) -- a plain str for
        every existing caller, with `.status` for callers that want the
        honest success/failed/stopped_after_retries/unable_to_verify/
        cancelled distinction (Phase 2). Reaching the end of the plan is
        NOT by itself treated as success — Phase 2: a plan that ran every
        step but never actually got a step to verify is reported as
        failed, not silently as if it had gone fine.
        """
        if not self._looks_multi_step(task):
            logger.info("Task looks single-step — skipping Planner call")
            return self.run_task(task, brain, session, initial_response=initial_response,
                                  cancel_event=cancel_event, on_event=on_event)

        plan = planner.decompose(task, self.settings, founder_context)
        if not plan:
            logger.info("No plan available — falling back to adaptive ReAct loop")
            return self.run_task(task, brain, session, initial_response=initial_response,
                                  cancel_event=cancel_event, on_event=on_event)

        logger.info(f"Plan created with {len(plan)} step(s) for task: {task}")
        self._safe_event(on_event, "planning", f"Plan created with {len(plan)} step(s)")
        observations = []
        steps_run = 0

        for i, planned_step in enumerate(plan):
            if cancel_event is not None and cancel_event.is_set():
                logger.info("Planned task cancelled by user request")
                result = "Stopped."
                self._safe_reflect(task, observations, result)
                return TaskOutcome(result, STATUS_CANCELLED)

            if steps_run >= MAX_STEPS:
                logger.warning(f"Planned task exceeded MAX_STEPS ({MAX_STEPS}) — stopping early")
                break
            steps_run += 1

            if i == 0 and initial_response is not None:
                response = initial_response
            else:
                step_prompt = self._build_planned_step_prompt(task, plan, planned_step, observations)
                session.user_input = step_prompt
                response = brain.process(session)

            if response.action and response.action != "none":
                self._safe_event(on_event, "executing",
                                  f"Step {planned_step['step']}: {planned_step['description']}")
                verified = self._execute_verified(
                    response.action, response.action_payload or {}, f"step {planned_step['step']}"
                )
                self._safe_event(on_event, "verifying",
                                  f"Step {planned_step['step']} "
                                  f"{'verified' if verified['success'] else 'failed verification'}")
                observation = verified["observation"]
                attempts = verified["attempts"]
                success = verified["success"]
            else:
                observation = response.text
                attempts = None
                success = True  # no action was taken — nothing to have failed

            observations.append({
                "step": planned_step["step"],
                "action": response.action,
                "payload": response.action_payload,
                "description": planned_step["description"],
                "observation": observation,
                "attempts": attempts,
                "success": success,
            })
            logger.info(f"Planned step {planned_step['step']}/{len(plan)}: {observation[:100]}")

            if self._is_stagnant(observations) or self._is_repeating_failed_action(observations):
                logger.warning(f"Stagnation detected — stuck repeating without progress "
                                f"{STAGNATION_WINDOW}x in a row, aborting the plan early")
                result = (f"I got stuck repeating the same approach without making "
                          f"progress ('{observation[:80]}'), so I stopped instead of "
                          f"continuing through the rest of the plan.")
                self._safe_reflect(task, observations, result)
                return TaskOutcome(result, STATUS_STOPPED_AFTER_RETRIES)

        final_text = observations[-1]["observation"] if observations else "Task could not be started."
        self._safe_reflect(task, observations, final_text)
        if not observations:
            return TaskOutcome(final_text, STATUS_FAILED)
        status = STATUS_FAILED if self._last_action_unresolved(observations) else STATUS_SUCCESS
        return TaskOutcome(final_text, status)

    def _safe_event(self, on_event, phase: str, message: str):
        """iQOO Phase 1 adapter: optional progress callback, additive and
        backward-compatible exactly like cancel_event above -- default
        None means zero behaviour change for any existing caller
        (main.py, telegram_bridge) that doesn't pass it. Never allowed to
        break or delay the task the callback is reporting on."""
        if on_event is None:
            return
        try:
            on_event(phase, message)
        except Exception as e:
            logger.debug(f"on_event callback skipped: {e}")

    def _safe_reflect(self, task: str, observations: list, outcome: str):
        """Reflection must never break or delay the response the user is
        waiting on — always call this after the result is already decided.
        Passes self.founder_mode through (may be None) so high-confidence
        lessons can bridge into Founder Mode when it's available."""
        try:
            self._reflection.reflect(task=task, steps=observations, outcome=outcome,
                                      founder_mode=self.founder_mode)
        except Exception as e:
            logger.debug(f"Reflection call skipped: {e}")

    def _build_planned_step_prompt(self, task: str, plan: list, current_step: Dict, observations: list) -> str:
        plan_text = "\n".join(f"{s['step']}. {s['description']}" for s in plan)
        obs_text = "\n".join(
            f"Step {o['step']} ({o['description']}): {o['observation']}" for o in observations
        ) if observations else "None yet."

        failure_note = ""
        if observations and not observations[-1].get("success", True):
            failure_note = (
                "\n\nThe most recent step above did not verify as successful even "
                "after a retry. Do not just repeat the same action for this step — "
                "re-check what's actually on screen and choose a different approach, "
                "or respond with action: null and an honest status if no reasonable "
                "alternative exists."
            )

        return (
            f"Overall task: {task}\n\n"
            f"Full plan:\n{plan_text}\n\n"
            f"Steps completed so far:\n{obs_text}{failure_note}\n\n"
            f"Now execute step {current_step['step']}: {current_step['description']}\n"
            f"If this step needs an action, specify it. If it's already satisfied by the "
            f"conversation so far, respond with action: null and a short status."
        )

    def _build_react_prompt(self, task: str, observations: list, current: str) -> str:
        if not observations:
            return f"Task: {task}\nWhat is the first action to take?"

        obs_text = "\n".join(
            f"Step {o['step']}: {o['action']} → {o['observation']}"
            for o in observations
        )
        return (
            f"Original task: {task}\n\n"
            f"Steps taken so far:\n{obs_text}\n\n"
            f"Current: {current}\n\n"
            f"What is the next action? If the task is complete, respond with action: null."
        )

    # ─── Action Executors ─────────────────────────────────────────────────

    def _execute_control(self, payload: Dict) -> str:
        controller = self._get_control()
        action_type = payload.get("type", "")

        if action_type == "click":
            description = payload.get("description", "")
            # First use vision to find where to click
            vision = self._get_vision()
            coords = vision.find_element(description)
            if not coords:
                return f"Could not find '{description}' on screen"

            controller.click(coords[0], coords[1])

            # Phase 1 (Hands reliability): OBSERVE AGAIN with a fresh
            # screenshot instead of reporting success purely because a
            # click command was issued. Re-look for the same target: if
            # it's still there in essentially the same spot, the click
            # most likely didn't register (stale/wrong coordinates, an
            # unresponsive control, or the UI hadn't finished rendering);
            # if it's gone or has moved well away from where it was,
            # that's real evidence the screen changed in response to the
            # click. This is a heuristic, not a guarantee — some elements
            # (e.g. Dock icons) legitimately stay visible after a
            # successful click — but it directly catches the concrete
            # failure mode from testing (clicking a Spotlight/menu/dialog
            # result that should dismiss and doesn't).
            recheck = vision.find_element(description)
            if recheck and self._same_spot(recheck, coords):
                return (f"Clicked '{description}' at {coords}, but the same "
                        f"target is still visible in the same place afterward "
                        f"— the click may not have registered.")
            return (f"Clicked on '{description}' at {coords}; it's no longer "
                    f"visible in the same spot afterward, consistent with the "
                    f"click taking effect.")

        elif action_type == "type":
            text = payload.get("text", "")
            controller.type_text(text)

            # Phase 1 (Hands reliability): give the next reasoning step
            # something real to look at instead of only its own request
            # echoed back. Previously this always returned a bare
            # "Typed: {text}" regardless of whether anything on screen
            # actually reflected it — with no observation of the
            # resulting state, the loop had no way to tell "it typed, now
            # click the result" from "nothing happened, try again", which
            # is exactly what produced the repeated "Typed: VS Code" loop
            # seen in testing.
            vision = self._get_vision()
            screen_state = vision.read(
                "Briefly describe what is currently visible on screen, "
                "especially any search box contents, search results, menu "
                "items, or dialogs. One or two sentences."
            )
            return f"Typed: {text}. Screen now shows: {screen_state}"

        elif action_type == "hotkey":
            keys = payload.get("keys", [])
            controller.hotkey(*keys)
            return f"Pressed hotkey: {keys}"

        elif action_type == "open_app":
            app = payload.get("app", "")
            controller.open_app(app)

            # Phase 1 (Hands reliability): verify the app actually became
            # frontmost instead of trusting that issuing the AppleScript
            # "activate" command without error means it's now open and in
            # front. Uses get_frontmost_app() (a direct, fast System
            # Events query) rather than a vision call — it's an exact
            # answer with no screenshot/LLM round-trip needed.
            matched, frontmost = self._poll_for_frontmost_match(controller, app)
            if matched:
                return f"Opened: {app}, confirmed in the foreground."
            if frontmost is None:
                return (f"Opened: {app} (could not confirm what's in the "
                        f"foreground afterward — see logs).")
            return (f"Opened: {app}, but '{frontmost}' is in the foreground "
                    f"instead — {app} may not have launched yet, may still "
                    f"be loading, or the name may not match exactly.")

        elif action_type == "screenshot":
            path = controller.screenshot()
            return f"Screenshot saved to {path}"

        return f"Unknown control action: {action_type}"

    def _execute_browser(self, payload: Dict) -> str:
        browser = self._get_browser()
        url = payload.get("url", "")
        task = payload.get("task", "")
        return browser.execute(url=url, task=task)

    def _execute_terminal(self, payload: Dict) -> str:
        terminal = self._get_terminal()
        command = payload.get("command", "")
        description = payload.get("description", "")
        return terminal.run(command, description)

    def _execute_vision(self, payload: Dict) -> str:
        vision = self._get_vision()
        task = payload.get("task", "read the screen")
        return vision.read(task)
