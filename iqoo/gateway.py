"""
iQOO — Task Gateway (Phase 1)

Thin adapter between the phone-facing HTTP API and SAM's existing
orchestration. Does NOT reimplement Brain, Planner, ReAct, Memory, or
Verification — it constructs the same objects the same way
ecosystem/telegram_bridge.py already does (a fully separate instance
set, not shared with main.py's voice/text process) and calls the exact
same entry points main.py calls: brain.process() then
react_loop.run_planned_task().

Concurrency: SAM's Hands (browser, vision, terminal) are not built for
concurrent execution — this is a standing invariant already enforced by
main.py's _process_lock and telegram_bridge's asyncio.Lock. This gateway
holds the same invariant with one dedicated worker thread processing a
FIFO queue of task_ids, so tasks submitted from the phone can never race
against each other or corrupt shared state (satisfies PDR 8.7's
"Repeated requests do not corrupt task state").
"""

import logging
import queue
import threading
from dataclasses import replace
from typing import Optional

from iqoo.task_store import TaskStore, TERMINAL_STATUSES
from iqoo.events import EventBus

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
            "version": "iqoo-phase1",
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
            # Phase 1 explicitly does not process image/voice attachments.
            # Fail safely and honestly rather than silently ignoring them
            # (PDR 9.3: never let unhandled perception fall through into
            # execution). Phase 2 replaces this branch.
            msg = (f"input_type '{record['input_type']}' is not yet supported — "
                   f"Phase 1 handles text tasks only. Multimodal input arrives in Phase 2.")
            self.task_store.update_status(task_id, "failed", error=msg)
            self.event_bus.publish(task_id, "failed", msg)
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
