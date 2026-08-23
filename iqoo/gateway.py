"""
iQOO — Task Gateway (Phase 1 + Phase 2)

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
from dataclasses import replace
from typing import Optional

from iqoo.task_store import TaskStore, TERMINAL_STATUSES
from iqoo.events import EventBus
from iqoo.errors import PerceptionError, PerceptionCancelled
from iqoo.vision_adapter import VisionAdapter
from iqoo.audio_adapter import AudioAdapter

logger = logging.getLogger("SAM.iQOO.Gateway")


class TaskGateway:
    def __init__(self, settings=None):
        if settings is None:
            from config.settings import Settings
            settings = Settings()
        self.settings = settings

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

        self._queue: "queue.Queue[str]" = queue.Queue()
        self._active_task_id: Optional[str] = None
        self._active_lock = threading.Lock()
        self._stop = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True,
                                         name="iqoo-task-worker")
        self._worker.start()

    # ─── Public API (called by iqoo/server.py) ─────────────────────────

    def submit_task(self, instruction: str, input_type: str = "text", attachments=None) -> str:
        task_id = self.task_store.create_task(instruction, input_type, attachments)
        self.event_bus.publish(task_id, "received", "Task received by SAM")
        self._queue.put(task_id)
        return task_id

    def get_task(self, task_id: str) -> Optional[dict]:
        return self.task_store.get_task(task_id)

    def cancel_task(self, task_id: str) -> bool:
        return self.task_store.request_cancel(task_id)

    def retry_task(self, task_id: str) -> Optional[str]:
        """Phase 1 retry: re-submits the same instruction as a fresh task.
        Simplest correct behaviour that satisfies the contract without
        adding a second execution path — a real "resume exactly where it
        left off" retry needs step-level checkpointing, which is Phase 3
        scope (task recovery), not Phase 1."""
        record = self.task_store.get_task(task_id)
        if not record:
            return None
        return self.submit_task(record["instruction"], record["input_type"], record["attachments"])

    def health(self) -> dict:
        with self._active_lock:
            active = self._active_task_id
        return {
            "status": "ok",
            "brain_reachable": self.brain._check_ollama(),
            "active_task": active,
            "queue_depth": self._queue.qsize(),
            "version": "iqoo-phase2",
        }

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
                self._process_task(task_id)
            except Exception as e:
                logger.error(f"Unhandled error processing task {task_id}: {e}", exc_info=True)
                self.task_store.update_status(task_id, "failed", error=str(e))
                self.event_bus.publish(task_id, "failed", f"Unhandled error: {e}")
            finally:
                with self._active_lock:
                    self._active_task_id = None
                self.task_store.cleanup_cancel_event(task_id)

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
