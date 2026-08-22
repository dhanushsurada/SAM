"""
iQOO — Execution Event Bus (Phase 1)

Task execution runs on a plain background thread (ReactLoop and the Hands
are synchronous, same as everywhere else in SAM). The HTTP server is
async (FastAPI/Starlette). This bus is the thread-safe bridge between the
two: publish() is called from the worker thread, and the SSE endpoint
reads from the same per-task queue via asyncio.to_thread() so a slow or
disconnected phone can never block the worker thread or other requests.

One queue per task_id. Not persisted — if the server restarts mid-task,
in-flight events are lost (the task's row in task_store.py is still the
source of truth for status; PROGRESS.md tracks this as a Phase 3
reconnect/recovery item, not a Phase 1 gap).
"""

import logging
import queue
import threading
from datetime import datetime
from typing import Dict

logger = logging.getLogger("SAM.iQOO.Events")

TERMINAL_PHASES = {"completed", "failed", "cancelled"}


class EventBus:
    def __init__(self):
        self._queues: Dict[str, "queue.Queue"] = {}
        self._lock = threading.Lock()

    def _get_queue(self, task_id: str) -> "queue.Queue":
        with self._lock:
            if task_id not in self._queues:
                self._queues[task_id] = queue.Queue()
            return self._queues[task_id]

    def publish(self, task_id: str, phase: str, message: str):
        event = {
            "type": "execution.step",
            "task_id": task_id,
            "phase": phase,
            "message": message,
            "timestamp": datetime.now().isoformat(),
        }
        self._get_queue(task_id).put(event)
        logger.debug(f"[{task_id}] {phase}: {message}")

    def subscribe_queue(self, task_id: str) -> "queue.Queue":
        return self._get_queue(task_id)

    def cleanup(self, task_id: str):
        """Drops the queue for a finished task. Safe to call more than
        once and safe to call while a subscriber still holds a reference
        to the old queue object (it'll just stop receiving new events)."""
        with self._lock:
            self._queues.pop(task_id, None)
