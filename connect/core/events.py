"""
SAM Connect — Event Bus

(New in agent/cross-device. Populates the "Event model" contract from
Master PDR section 16 — "Task, voice, device and runtime events" — for
cross-device traffic specifically. interfaces/api/events.py already has
an execution-event bus for a single task's own SSE stream; this is not a
replacement for that one, it's the same pattern applied one level up, to
the vocabulary the Agent 3 execution prompt's section 7 asks for:

    device.connected, device.disconnected, device.updated
    task.created, task.started, task.progress, task.action,
        task.verification, task.completed, task.failed, task.cancelled
    voice.started, voice.stopped

("task.cancelled" is one addition beyond that list — section 6 asks for
"cancellation where supported" and section 9 asks for meaningful states
on a cancelled/duplicate request, and every other terminal task outcome
in this vocabulary has its own event, so a silently-missing one for
cancellation would be the odd one out. Documented here rather than
snuck in quietly.)

Same concurrency design as interfaces/api/events.py, and deliberately
so — it's already a correct, tested solution to "a background thread
publishes, an async HTTP handler consumes, and a reconnecting client
must be able to replay only what it missed" — this module just keys it
by an arbitrary *stream* string instead of a task_id, since cross-device
events aren't all about one task: "give me every event for device X",
"give me every event for task Y", and "give me every device/task event
system-wide" (the Devices page's live view) are all real subscriptions a
caller needs, not just one.

Stream naming convention (enforced by convention, not by this class):
    "device"                     — every device.* event, all devices
    "device:<external_id>"       — device.* events for one device
    "task:<task_id>"             — every event for one routed task
    "voice"                      — every voice.* event

connect/services/task_handoff.py and connect/transports/lan_http.py
publish to more than one stream per event (e.g. a task.progress event
for device X goes to both "task:<task_id>" and "device:X") — see
ConnectEventBus.publish_to.
"""

import logging
import threading
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("SAM.Connect.Events")

DEVICE_EVENT_TYPES = frozenset({"device.connected", "device.disconnected", "device.updated"})
TASK_EVENT_TYPES = frozenset({
    "task.created", "task.started", "task.progress", "task.action",
    "task.verification", "task.completed", "task.failed", "task.cancelled",
})
VOICE_EVENT_TYPES = frozenset({"voice.started", "voice.stopped"})
ALL_EVENT_TYPES = DEVICE_EVENT_TYPES | TASK_EVENT_TYPES | VOICE_EVENT_TYPES

# Same three type-tags as interfaces/api/events.py's TERMINAL_PHASES, applied
# to this module's task.* vocabulary instead of task_store.py's status
# strings — a task stream stops accepting new events once one of these has
# been published, for the identical reason: an orphaned late-finishing
# dispatch must not be able to append after a reconnecting client already
# saw the terminal outcome.
TERMINAL_TASK_EVENT_TYPES = frozenset({"task.completed", "task.failed", "task.cancelled"})


class UnknownEventTypeError(ValueError):
    pass


class ConnectEventBus:
    def __init__(self):
        self._history: Dict[str, List[dict]] = {}
        self._conditions: Dict[str, threading.Condition] = {}
        self._lock = threading.Lock()

    def _get_condition(self, stream: str) -> threading.Condition:
        with self._lock:
            if stream not in self._conditions:
                self._conditions[stream] = threading.Condition()
                self._history[stream] = []
            return self._conditions[stream]

    def publish(self, stream: str, event_type: str, **fields) -> Optional[dict]:
        """Publishes one event to one stream. `fields` becomes the
        event's payload alongside `type`/`stream`/`seq`/`timestamp` —
        e.g. publish("task:abc", "task.progress", task_id="abc",
        message="opening app", pct=40). Returns None (and logs, doesn't
        raise) if `stream` already has a terminal task event — same
        "terminal is final" guard as interfaces/api/events.py.publish,
        so a caller can fire-and-forget without checking has_terminal_event
        itself every time."""
        if event_type not in ALL_EVENT_TYPES:
            raise UnknownEventTypeError(
                f"'{event_type}' is not a known Connect event type — see connect.core.events.ALL_EVENT_TYPES"
            )
        cond = self._get_condition(stream)
        with cond:
            history = self._history[stream]
            if any(e["type"] in TERMINAL_TASK_EVENT_TYPES for e in history):
                logger.debug(f"Ignoring '{event_type}' on stream '{stream}' — already terminal")
                return None
            seq = len(history) + 1
            event = {"type": event_type, "stream": stream, "seq": seq,
                      "timestamp": datetime.now().isoformat(), **fields}
            history.append(event)
            cond.notify_all()
        logger.debug(f"[{stream}] #{seq} {event_type}")
        return event

    def publish_to(self, streams: List[str], event_type: str, **fields) -> List[Optional[dict]]:
        """Publishes the same logical event to several streams at once
        (e.g. a task event goes to both "task:<id>" and
        "device:<external_id>") — each stream gets its own seq number
        appropriate to its own history, not a shared one, since each is
        independently replayable."""
        return [self.publish(s, event_type, **fields) for s in streams]

    def get_since(self, stream: str, after_seq: int = 0) -> List[dict]:
        cond = self._get_condition(stream)
        with cond:
            return [e for e in self._history.get(stream, []) if e["seq"] > after_seq]

    def wait_for_new(self, stream: str, after_seq: int, timeout: float = 1.0) -> List[dict]:
        """Blocks up to `timeout` seconds for a new event, then returns
        everything after after_seq (possibly more than one). Empty list
        on timeout is the caller's heartbeat cue, not an error — same
        contract as interfaces/api/events.py.wait_for_new."""
        cond = self._get_condition(stream)
        with cond:
            cond.wait_for(lambda: len(self._history.get(stream, [])) > after_seq, timeout=timeout)
            return [e for e in self._history.get(stream, []) if e["seq"] > after_seq]

    def latest_seq(self, stream: str) -> int:
        cond = self._get_condition(stream)
        with cond:
            return len(self._history.get(stream, []))

    def has_terminal_event(self, stream: str) -> bool:
        cond = self._get_condition(stream)
        with cond:
            return any(e["type"] in TERMINAL_TASK_EVENT_TYPES for e in self._history.get(stream, []))

    def cleanup(self, stream: str):
        with self._lock:
            self._conditions.pop(stream, None)
            self._history.pop(stream, None)

    def reset_all(self):
        """Testing/demo-reset only — mirrors
        interfaces/api/events.py.EventBus.reset_all."""
        with self._lock:
            self._conditions.clear()
            self._history.clear()
