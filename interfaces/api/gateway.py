"""
SAM Interfaces — API — Task Gateway (Phase 1 + Phase 2 + Phase 3A reliability)

(Moved here in Phase 3A.5 — originated as iqoo/gateway.py. This is the
phone-task HTTP interface's own implementation, not a component other
interfaces call into — Telegram has its own separate construction of
the same Core stack, same as before. iqoo/gateway.py now forwards here
for backward compatibility.)

Thin adapter between the phone-facing HTTP API and SAM's existing
orchestration. Does NOT reimplement Brain, Planner, ReAct, Memory, or
Verification — it constructs the same objects the same way
ecosystem/telegram_bridge.py already does (a fully separate instance
set, not shared with main.py's voice/text process) and calls the exact
same entry points main.py calls: brain.process() then
react_loop.run_planned_task().

Phase 2 adds one step before that: for image/voice tasks, _perceive()
(below) turns the phone's attachments into plain text context via
VisionAdapter/AudioAdapter, then hands that text to the exact same
Brain/Planner/ReAct path a typed task already used in Phase 1. The
Brain never sees an image or audio byte — only text, exactly as before.

Phase 3A adds reliability around all of that without touching any of
it: a hard per-task timeout watchdog, startup recovery for tasks
orphaned by a server restart, retry validation, an explicit demo reset,
and richer health diagnostics. See docs/iqoo/ARCHITECTURE.md's Phase 3A
section for the timeout design's honest trade-off (it cannot forcibly
kill a stuck synchronous Hands call — nothing in Python can, short of
killing the process — so it reports failure to the phone immediately
but the worker still waits for the orphaned thread to actually finish
before touching Hands again, to preserve the single-flight invariant
below).

Concurrency: SAM's Hands (browser, vision, terminal) are not built for
concurrent execution — this is a standing invariant already enforced by
main.py's _process_lock and telegram_bridge's asyncio.Lock. This gateway
holds the same invariant with one dedicated worker thread processing a
FIFO queue of task_ids, so tasks submitted from the phone can never race
against each other or corrupt shared state (satisfies PDR 8.7's
"Repeated requests do not corrupt task state"). Perception (Phase 2)
runs on this same single worker thread, so it is serialized exactly like
everything else — no separate perception concurrency model was added.
"""

import logging
import queue
import threading
import time
from dataclasses import replace
from typing import Optional

from interfaces.api.task_store import TaskStore, TERMINAL_STATUSES
from interfaces.api.events import EventBus
from multimodal.errors import PerceptionError, PerceptionCancelled
from multimodal.vision.adapter import VisionAdapter
from multimodal.audio.adapter import AudioAdapter

logger = logging.getLogger("SAM.iQOO.Gateway")

# Phase 3A: hard ceiling on a single task's total processing time
# (perception + understanding + planning + execution + verification
# combined), measured from the worker's perspective. 10 minutes is
# generous for the whiteboard-to-backend demo (which involves an LLM
# call, a vision call, and real code generation/test execution) while
# still catching a genuinely stuck Hands call before it can silently
# stall the entire competition demo for the rest of the event slot.
DEFAULT_TASK_TIMEOUT_SECONDS = 600


class TaskAlreadyActiveError(Exception):
    """Raised by retry_task() when asked to retry a task that hasn't
    reached a terminal status yet — retrying a still-running task would
    create two competing attempts at the same instruction and make
    "which one is real" ambiguous, which is exactly the kind of
    confusing state Phase 3A's retry-safety requirement exists to
    prevent."""


class DemoResetBusyError(Exception):
    """Raised by reset_demo_state() when the worker is mid-task or the
    queue isn't empty — resetting out from under a running task would
    corrupt whatever it's doing without actually stopping it (nothing
    forcibly kills Hands calls — see the module docstring)."""


class TaskGateway:
    def __init__(self, settings=None, task_timeout_seconds: int = DEFAULT_TASK_TIMEOUT_SECONDS):
        if settings is None:
            from config.settings import Settings
            settings = Settings()
        self.settings = settings
        self.task_timeout_seconds = task_timeout_seconds

        # Same construction pattern as main.py / telegram_bridge.py.
        from memory.identity import Identity
        from memory.retrieve import MemoryRetriever
        from founder_mode.manager import FounderModeManager
        from core.brain import Brain
        from agent.react_loop import ReactLoop

        self.identity = Identity()
        self.memory = MemoryRetriever()
        self.founder_mode = FounderModeManager(settings=settings)
        self.brain = Brain(settings)
        self.react_loop = ReactLoop(settings, founder_mode=self.founder_mode)

        self.task_store = TaskStore()
        self.event_bus = EventBus()
        self.vision_adapter = VisionAdapter(settings)
        self.audio_adapter = AudioAdapter(settings)

        # Phase 3A: a task left non-terminal by a previous process (crash
        # or restart mid-task) has no worker left to ever finish it —
        # recover those immediately so the API never shows a task stuck
        # forever in a phantom "executing" state after a restart.
        self.task_store.recover_orphaned_tasks()

        self._queue: "queue.Queue[str]" = queue.Queue()
        self._active_task_id: Optional[str] = None
        self._active_lock = threading.Lock()
        self._stop = threading.Event()
        self._started_at = time.time()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True,
                                         name="iqoo-task-worker")
        self._worker.start()

    # ─── Public API (called by interfaces/api/server.py) ────────────────

    def submit_task(self, instruction: str, input_type: str = "text", attachments=None,
                     retried_from: Optional[str] = None) -> str:
        task_id = self.task_store.create_task(instruction, input_type, attachments, retried_from)
        self.event_bus.publish(task_id, "received", "Task received by SAM")
        self._queue.put(task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        return self.task_store.get_task(task_id)

    def cancel_task(self, task_id: str) -> bool:
        return self.task_store.request_cancel(task_id)

    def retry_task(self, task_id: str) -> Optional[str]:
        """Re-submits the original instruction/attachments as a NEW
        task_id, linked back via retried_from for debugging history.
        Does not resume mid-plan — that needs step-level checkpointing,
        which remains out of scope (Phase 3A hardens what exists rather
        than adding new execution semantics).

        Phase 3A: only allowed once the original task has reached a
        terminal status. Retrying a still-active task would create two
        competing attempts at the same instruction racing through the
        same single worker/Hands, which is exactly the "task pretending
        to be active twice" scenario the reliability checkpoint calls
        out — raises TaskAlreadyActiveError instead of silently allowing
        it, same as before this was a real (if narrow) latent bug."""
        record = self.task_store.get_task(task_id)
        if not record:
            return None
        if record["status"] not in TERMINAL_STATUSES:
            raise TaskAlreadyActiveError(
                f"Task {task_id} is still '{record['status']}' — cancel it first or wait for it to finish")
        return self.submit_task(record["instruction"], record["input_type"], record["attachments"],
                                 retried_from=task_id)

    def health(self) -> dict:
        with self._active_lock:
            active = self._active_task_id
        worker_alive = self._worker.is_alive()
        brain_reachable = self.brain._check_ollama()
        vision_available = self.vision_adapter.model_available() if brain_reachable else None
        whisper_available = self.audio_adapter.whisper_installed()

        status = "ok" if (worker_alive and brain_reachable) else "degraded"

        return {
            "status": status,
            "worker_alive": worker_alive,
            "brain_reachable": brain_reachable,
            "vision_model_available": vision_available,
            "whisper_available": whisper_available,
            "active_task": active,
            "queue_depth": self._queue.qsize(),
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "version": "iqoo-phase3a",
        }

    def reset_demo_state(self) -> int:
        """Phase 3A: clears every task row and all event history. Refuses
        while the worker is busy or the queue is non-empty, so a reset
        can never be issued out from under a task that's actually
        running — the caller (interfaces/api/server.py's /api/iqoo/demo/reset
        endpoint) surfaces DemoResetBusyError as a 409, telling the
        organizer/presenter to cancel or wait first. Never touches
        memory/store.py or founder_mode's store — see
        TaskStore.reset_demo_state's docstring."""
        with self._active_lock:
            active = self._active_task_id
        if active is not None or self._queue.qsize() > 0:
            raise DemoResetBusyError(
                "Cannot reset while a task is active or queued — cancel or wait for it to finish first")
        deleted = self.task_store.reset_demo_state()
        self.event_bus.reset_all()
        logger.warning(f"Demo reset complete: {deleted} task(s) cleared")
        return deleted

    def shutdown(self):
        self._stop.set()

    # ─── Worker ─────────────────────────────────────────────────────────

    def _worker_loop(self):
        while not self._stop.is_set():
            try:
                task_id = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            with self._active_lock:
                self._active_task_id = task_id
            try:
                self._run_task_with_timeout(task_id)
            except Exception as e:
                logger.error(f"Unhandled error processing task {task_id}: {e}", exc_info=True)
                self.task_store.update_status(task_id, "failed", error=str(e))
                self.event_bus.publish(task_id, "failed", f"Unhandled error: {e}")
            finally:
                with self._active_lock:
                    self._active_task_id = None
                self.task_store.cleanup_cancel_event(task_id)

    def _run_task_with_timeout(self, task_id: str):
        """Runs _process_task on a dedicated thread with a hard
        wall-clock ceiling (self.task_timeout_seconds). If it doesn't
        finish in time, the phone is told immediately ('failed', with a
        timeout reason) instead of waiting indefinitely.

        Honest trade-off, documented rather than hidden: this FIFO
        worker thread still blocks until the orphaned _process_task
        thread actually returns before picking up the next queued task.
        Nothing in Python can forcibly stop a thread blocked inside a
        synchronous Hands call or a network request with no timeout of
        its own — the only real way to kill it is to kill the process.
        Letting a second task touch the same (non-concurrency-safe)
        Hands while the first might still be mid-action would be worse
        than a slow recovery, so this waits it out rather than risk that.
        See docs/iqoo/ARCHITECTURE.md's Phase 3A section.
        """
        done = threading.Event()
        error_holder = {}

        def _run():
            try:
                self._process_task(task_id)
            except Exception as e:
                # Belt-and-suspenders: _process_task already catches
                # exceptions inside its own "understanding onward"
                # block, but anything raised earlier (the cancellation
                # pre-checks, or _perceive() itself for a bug other than
                # PerceptionError/PerceptionCancelled) would otherwise
                # propagate out of this thread silently — Python threads
                # swallow uncaught exceptions rather than crashing the
                # process, which would leave the task stuck in whatever
                # non-terminal status it last had, forever. This was a
                # real bug caught while writing
                # tests/test_iqoo_phase3a_offline.py's worker-recovery
                # test, introduced by this exact refactor (moving
                # _process_task onto a nested thread for the timeout
                # watchdog) — fixed before it ever shipped.
                error_holder["exception"] = e
            finally:
                done.set()

        worker_thread = threading.Thread(target=_run, daemon=True,
                                          name=f"iqoo-task-{task_id[:8]}")
        worker_thread.start()
        finished_in_time = done.wait(timeout=self.task_timeout_seconds)

        if finished_in_time:
            if "exception" in error_holder:
                e = error_holder["exception"]
                logger.error(f"Unhandled error processing task {task_id}: {e}", exc_info=True)
                self.task_store.update_status(task_id, "failed", error=str(e))
                self.event_bus.publish(task_id, "failed", f"Unhandled error: {e}")
            return

        logger.warning(f"Task {task_id} exceeded {self.task_timeout_seconds}s — timing out")
        # Best-effort interrupt: react_loop/_perceive check cancel_event
        # between discrete steps, so a task currently between steps
        # (rather than stuck inside one unbounded call) may actually
        # stop promptly even though we don't wait for it to confirm that
        # before reporting failure to the phone.
        self.task_store.get_cancel_event(task_id).set()
        self.task_store.update_status(
            task_id, "failed", error=f"Task timed out after {self.task_timeout_seconds}s")
        self.event_bus.publish(task_id, "failed",
                                f"Task timed out after {self.task_timeout_seconds}s")

        while not done.is_set() and not self._stop.is_set():
            done.wait(timeout=1.0)
        if not done.is_set():
            logger.warning(
                f"Gateway shutting down while task {task_id}'s orphaned thread was still running")

    def _process_task(self, task_id: str):
        record = self.task_store.get_task(task_id)
        if record is None:
            return

        cancel_event = self.task_store.get_cancel_event(task_id)
        if cancel_event.is_set():
            self.task_store.update_status(task_id, "cancelled", result_text="Cancelled before start.")
            self.event_bus.publish(task_id, "cancelled", "Cancelled before execution started")
            return

        instruction = record["instruction"]
        if record["input_type"] != "text":
            self.task_store.update_status(task_id, "perceiving")
            self.event_bus.publish(task_id, "perceiving", "Interpreting attachments")
            try:
                instruction = self._perceive(record, cancel_event)
            except PerceptionCancelled:
                self.task_store.update_status(task_id, "cancelled",
                                               result_text="Cancelled during perception.")
                self.event_bus.publish(task_id, "cancelled", "Cancelled during perception")
                return
            except PerceptionError as e:
                logger.warning(f"Perception failed for task {task_id}: {e}")
                self.task_store.update_status(task_id, "failed", error=str(e))
                self.event_bus.publish(task_id, "failed", f"Couldn't understand the attachment: {e}")
                return
            self.event_bus.publish(task_id, "perceiving", "Attachments understood")

            # Perception adapters make blocking HTTP/model calls that can't
            # be interrupted mid-flight — cancel_event can only be observed
            # before or after each call, never during. Check again here,
            # immediately after perception finishes, so a cancellation
            # requested while a slow vision/audio call was in flight is
            # caught the moment that call returns, rather than silently
            # falling through into brain.process() (which happened, and
            # was a real bug caught by
            # test_gateway_cancellation_during_perception in
            # tests/test_iqoo_phase2_offline.py).
            if cancel_event.is_set():
                self.task_store.update_status(task_id, "cancelled",
                                               result_text="Cancelled after perception completed.")
                self.event_bus.publish(task_id, "cancelled", "Cancelled after perception completed")
                return

        self.task_store.update_status(task_id, "understanding")
        self.event_bus.publish(task_id, "understanding", "Reading your request")

        from core.session import Session
        from licensing.tier import get_tier, PRO, FREE_TIER_MEMORY_RETENTION_DAYS

        try:
            retention_days = None if get_tier(self.settings) == PRO else FREE_TIER_MEMORY_RETENTION_DAYS
            session = Session(
                user_input=instruction,
                identity=self.identity.load(),
                memories=self.memory.retrieve(instruction, self.settings, retention_days=retention_days),
                founder_context=self.founder_mode.get_context(),
                settings=self.settings,
            )

            response = self.brain.process(session)

            if cancel_event.is_set():
                self.task_store.update_status(task_id, "cancelled", result_text="Cancelled.")
                self.event_bus.publish(task_id, "cancelled", "Cancelled during understanding")
                return

            final_response = response

            if response.action and response.action not in (None, "none"):
                def _on_event(phase: str, message: str):
                    self.task_store.update_status(task_id, phase)
                    self.event_bus.publish(task_id, phase, message)

                real_result_text = self.react_loop.run_planned_task(
                    task=instruction,
                    brain=self.brain,
                    session=session,
                    founder_context=session.founder_context,
                    initial_response=response,
                    cancel_event=cancel_event,
                    on_event=_on_event,
                )
                final_response = replace(response, text=real_result_text)

            if cancel_event.is_set():
                self.task_store.update_status(task_id, "cancelled", result_text=final_response.text)
                self.event_bus.publish(task_id, "cancelled", "Cancelled during execution")
                return

            if not self.settings.incognito:
                session.save(user_input=instruction, response=final_response,
                             memory_store=self.memory.get_store(self.settings))
            self.founder_mode.capture_if_relevant(instruction, final_response)

            self.task_store.update_status(task_id, "completed", result_text=final_response.text)
            self.event_bus.publish(task_id, "completed", final_response.text)

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}", exc_info=True)
            self.task_store.update_status(task_id, "failed", error=str(e))
            self.event_bus.publish(task_id, "failed", f"I hit an error: {e}")

    def _perceive(self, record: dict, cancel_event) -> str:
        """Turns a non-text task's attachments into a single enriched
        instruction string, then hands that string to the exact same
        brain.process()/run_planned_task() path a text task uses — the
        Brain, Planner, and ReAct loop never know whether the instruction
        originated as typed text or as a phone photo + voice note. This
        is the entire adapter contract: perception produces text context,
        it does not plan or execute anything itself.

        Raises PerceptionError (interpretation failed) or
        PerceptionCancelled (cancel requested mid-perception) — both
        handled distinctly by the caller.
        """
        input_type = record["input_type"]
        attachments = record["attachments"]
        base_instruction = (record["instruction"] or "").strip()

        image_att = next((a for a in attachments if a.get("kind") == "image"), None)
        audio_att = next((a for a in attachments if a.get("kind") == "audio"), None)

        if input_type == "voice" and audio_att is None:
            raise PerceptionError("input_type 'voice' declared but no audio attachment was found")
        if input_type in ("image", "image+text") and image_att is None:
            raise PerceptionError(f"input_type '{input_type}' declared but no image attachment was found")
        if input_type == "image+voice" and (image_att is None or audio_att is None):
            raise PerceptionError("input_type 'image+voice' requires both an image and an audio attachment")

        spoken_text = None
        if audio_att is not None and input_type in ("voice", "image+voice"):
            if cancel_event.is_set():
                raise PerceptionCancelled()
            spoken_text = self.audio_adapter.transcribe(audio_att)

        vision_context = None
        if image_att is not None and input_type in ("image", "image+text", "image+voice"):
            if cancel_event.is_set():
                raise PerceptionCancelled()
            # Prefer the transcribed speech to frame vision's task, not the
            # typed instruction field: the primary demo workflow (PDR
            # section 9) is "speak the real instruction while pointing the
            # camera," so for image+voice the typed `instruction` field is
            # typically just a required placeholder (e.g. "(voice
            # command)"), not the substantive request. Falling back to
            # spoken_text first — not base_instruction first — was a real
            # bug caught by test_gateway_image_voice_task_combines_both in
            # tests/test_iqoo_phase2_offline.py: vision was being framed by
            # the placeholder text instead of what the user actually said.
            vision_instruction = spoken_text or base_instruction or "Describe this image thoroughly."
            vision_context = self.vision_adapter.interpret(image_att, vision_instruction)

        combined = base_instruction
        if spoken_text:
            combined = f"{combined}\n{spoken_text}".strip() if combined else spoken_text
        if vision_context:
            combined = (
                f"{combined}\n\n[Image context — SAM's vision model analysis of the attached photo]\n"
                f"{vision_context}\n[End image context]"
            ).strip()

        if not combined:
            raise PerceptionError("No usable instruction could be derived from the attachments")

        return combined
