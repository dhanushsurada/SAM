"""
iQOO — Execution Event Bus (Phase 1, redesigned in Phase 3A)

Task execution runs on a plain background thread (ReactLoop and the
Hands are synchronous, same as everywhere else in SAM). The HTTP server
is async (FastAPI/Starlette). This bus is the thread-safe bridge
between the two.

Phase 3A change: Phase 1/2 kept only a single ephemeral queue.Queue per
task, drained (destructively) by whichever SSE connection was reading
it, and the server eagerly called cleanup() the moment any stream
closed. That meant a reconnecting phone — after a dropped WiFi hop, a
browser refresh, or backgrounding the tab — got a queue that either had
already lost every event before the point it reconnected, or had been
deleted outright, silently losing the terminal completed/failed/
cancelled event. That was the real Phase 3A "SSE reliability" gap.

This version keeps a full ordered, sequence-numbered history per task
instead of a single-consumer queue. Reconnecting is now just "ask for
every event after sequence number N" (N=0 replays everything) — the
same mechanism the SSE spec's own `Last-Event-ID` header is designed
for, wired up in iqoo/server.py. History is not deleted when a stream
disconnects; it's deleted only by an explicit demo reset
(TaskGateway.reset_demo_state) or never, for the lifetime of the
process — bounded by the number of tasks in a single demo session, not
by traffic, so this is not a real memory concern for the hackathon's
scope.
"""

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("SAM.iQOO.Events")

TERMINAL_PHASES = {"completed", "failed", "cancelled"}


class EventBus:
    def __init__(self):
        self._history: Dict[str, List[dict]] = {}
        self._conditions: Dict[str, threading.Condition] = {}
        self._lock = threading.Lock()

    def _get_condition(self, task_id: str) -> threading.Condition:
        with self._lock:
            if task_id not in self._conditions:
                self._conditions[task_id] = threading.Condition()
                self._history[task_id] = []
            return self._conditions[task_id]

    def publish(self, task_id: str, phase: str, message: str) -> Optional[dict]:
        cond = self._get_condition(task_id)
        with cond:
            history = self._history[task_id]
            # Phase 3A: once a terminal event has been published for a
            # task, no further event is added — the same "terminal state
            # is final" guard as TaskStore.update_status, for the same
            # reason (an orphaned thread from a timed-out task finishing
            # late must not be able to append a post-terminal event that
            # a freshly reconnecting phone would then see in its replay).
            if any(e["phase"] in TERMINAL_PHASES for e in history):
                logger.debug(f"Ignoring event '{phase}' for task {task_id} — already has a terminal event")
                return None
            seq = len(history) + 1
            event = {
                "type": "execution.step",
                "task_id": task_id,
                "seq": seq,
                "phase": phase,
                "message": message,
                "timestamp": datetime.now().isoformat(),
            }
            history.append(event)
            cond.notify_all()
        logger.debug(f"[{task_id}] #{seq} {phase}: {message}")
        return event

    def get_since(self, task_id: str, after_seq: int = 0) -> List[dict]:
        """Every event with seq > after_seq, in order. after_seq=0 (the
        default) returns the full history — this is what a phone
        reconnecting cold (no Last-Event-ID, e.g. a fresh page load
        while a task is still running) uses to instantly recover full
        current state instead of waiting for the next new event."""
        cond = self._get_condition(task_id)
        with cond:
            history = self._history.get(task_id, [])
            return [e for e in history if e["seq"] > after_seq]

    def wait_for_new(self, task_id: str, after_seq: int, timeout: float = 1.0) -> List[dict]:
        """Blocks up to `timeout` seconds for at least one event with
        seq > after_seq to exist, then returns everything after
        after_seq (possibly more than one, if several were published
        while this call was waiting). Returns an empty list on timeout —
        callers use that as their heartbeat cue, not an error."""
        cond = self._get_condition(task_id)
        with cond:
            cond.wait_for(lambda: len(self._history.get(task_id, [])) > after_seq, timeout=timeout)
            history = self._history.get(task_id, [])
            return [e for e in history if e["seq"] > after_seq]

    def latest_seq(self, task_id: str) -> int:
        cond = self._get_condition(task_id)
        with cond:
            return len(self._history.get(task_id, []))

    def has_terminal_event(self, task_id: str) -> bool:
        cond = self._get_condition(task_id)
        with cond:
            return any(e["phase"] in TERMINAL_PHASES for e in self._history.get(task_id, []))

    def cleanup(self, task_id: str):
        """Drops all history for a task. NOT called automatically on
        stream disconnect anymore (that was the Phase 1/2 bug) — only
        called by an explicit demo reset, so reconnect keeps working for
        the lifetime of the process otherwise."""
        with self._lock:
            self._conditions.pop(task_id, None)
            self._history.pop(task_id, None)

    def reset_all(self):
        """Used by TaskGateway.reset_demo_state() only."""
        with self._lock:
            self._conditions.clear()
            self._history.clear()
