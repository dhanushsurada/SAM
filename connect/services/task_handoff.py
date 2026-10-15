"""
SAM Connect — Task Routing & Context Handoff

(New in agent/cross-device. Implements three items from the Agent 3
execution prompt at once, because they turned out to be one data model,
not three: section 6 "Task routing" — Desktop -> Android and Android ->
Desktop/Core — section 7 "Event model" wiring for task.*, and section 8
"Context handoff".)

=== What this is NOT ===
This is not interfaces/api/task_store.py, and does not replace it.
task_store.py is SAM Core's own record of instructions the phone sends
IT to execute locally (Brain -> ReactLoop, states like "understanding" /
"planning" / "verifying" that only make sense for Core's own AI
pipeline). A DeviceTask here is different in kind: SAM routes it TO a
device for that device to execute with ITS OWN capabilities
(connect.core.capabilities) — SAM Core's Brain/Planner never touch it.
"Open Instagram on my phone" is a DeviceTask targeting an Android device;
an ordinary phone-submitted instruction stays exactly what it always
was, a task_store.py row. Per the Agent 3 execution prompt's own
guardrail ("Do not build a second memory system... SAM Core remains the
source of truth for memory"), context_ref/handoff_state below are opaque
pointers this module carries on Core's behalf, never a second copy of
Core's own session/memory state.

=== Task lifecycle ===

    created -> dispatched -------> started -> in_progress -> completed
                  \\                                       -> failed
                   -> queued_offline -> (redelivered on     -> cancelled
                                          reconnect) ---^    -> timed_out

- created: row exists, capability pre-checked, not yet handed to a
  transport.
- dispatched: target device was online at dispatch time; a transport
  (connect/transports/lan_http.py's heartbeat/pending-tasks path today)
  is responsible for actually getting it to the device.
- queued_offline: target device was offline; sits here until the same
  device's next successful heartbeat, which calls get_pending_for_device
  and redelivers it (-> dispatched) — see connect/transports/lan_http.py
  and interfaces/api/connect_routes.py's heartbeat handler.
- started: the device itself called ack() — proof it actually received
  and began the task, not just that SAM attempted delivery.
- in_progress: at least one progress()/action()/verification() call
  landed.
- completed / failed / cancelled / timed_out: terminal. Once here,
  connect.core.events.ConnectEventBus's own terminal guard stops any
  further event on this task's stream, matching interfaces/api/events.py's
  identical rule for its own task streams.

=== Idempotency ===
create() takes an optional idempotency_key. A second create() with the
same (target_device_id, idempotency_key) pair returns the *original*
DeviceTask instead of creating another one — see spec section 9's
"duplicate requests" and section 14's test list. This is a deliberate,
narrow reading of idempotency: same key, same target device, same
result, no matter how many times the caller (a flaky LAN connection
retrying a POST) asks.

=== Context handoff ===
handoff() moves a task's *thread* to a new device without losing its
identity: it creates a new DeviceTask with handoff_of set to the
original task_id (same convention as interfaces/api/task_store.py's
retried_from for retries), copies context_ref/handoff_state across
unchanged, and cancels the original if it wasn't already terminal. The
event history of the *original* task_id is untouched and still queryable
— "a task should not become a completely separate task merely because
the user changes devices" (Agent 3 execution prompt, section 8) is
satisfied by handoff_of being a real, traceable link, not by pretending
it's literally still the same task_id.
"""

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from connect.core.capabilities import device_supports
from connect.core.device_registry import DeviceRegistry, DIRECT_CHANNEL
from connect.core.events import ConnectEventBus

logger = logging.getLogger("SAM.Connect.TaskHandoff")

# Separate data directory from both connect/core/device_registry.py's
# ecosystem/devices.db and interfaces/api/task_store.py's iqoo/tasks.db —
# same "Local Data Separation" principle both of those already follow:
# routed-task bookkeeping is its own concern, kept apart even though all
# three live under ~/.sam_data/ locally.
SAM_DATA_DIR = Path.home() / ".sam_data"
CONNECT_DIR = SAM_DATA_DIR / "connect"
DEVICE_TASKS_DB_PATH = CONNECT_DIR / "device_tasks.db"

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "timed_out"})
ALL_STATUSES = frozenset({"created", "dispatched", "queued_offline", "started", "in_progress"}) | TERMINAL_STATUSES

# How long a task may sit with no update from the device before
# sweep_timeouts() fails it out. Generous default for an unknown action;
# callers doing something they know is quick/slow should pass their own
# timeout_seconds to create().
DEFAULT_TIMEOUT_SECONDS = 300


class TaskRoutingError(Exception):
    """Base class for every reason this module refuses to route or
    update a task. interfaces/api/connect_routes.py maps each subclass
    to a specific HTTP status (see docs/architecture/CROSS_DEVICE_PROTOCOL.md)."""


class UnknownDeviceError(TaskRoutingError):
    """target_device_id is not a currently-trusted device."""


class CapabilityUnavailableError(TaskRoutingError):
    """The target device hasn't reported this capability as both
    available and permission-granted. Raised at create() time,
    deliberately before a row even exists — "do not claim capabilities
    that are unavailable or denied" (Agent 3 execution prompt, section 5)
    means refusing up front, not queuing something that can never
    succeed."""


class TaskNotFoundError(TaskRoutingError):
    pass


class TaskNotOwnedByDeviceError(TaskRoutingError):
    """A device tried to ack/update a task routed to a *different*
    device_id. Always a bug or a spoofed request, never a legitimate
    race — connect/transports/lan_http.py has already proven the
    caller's identity by this point, so this check is about routing
    correctness, not authentication."""


class InvalidTaskStateError(TaskRoutingError):
    """E.g. trying to ack() a task that's already terminal."""


@dataclass
class DeviceTask:
    task_id: str
    origin: str
    target_device_id: str
    action: str
    payload: Dict = field(default_factory=dict)
    required_capability: Optional[str] = None
    status: str = "created"
    result: Optional[Dict] = None
    error: Optional[str] = None
    last_message: Optional[str] = None
    last_pct: Optional[int] = None
    idempotency_key: Optional[str] = None
    context_ref: Optional[str] = None
    handoff_state: Optional[Dict] = None
    handoff_of: Optional[str] = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    created_at: str = ""
    updated_at: str = ""

    @property
    def streams(self) -> List[str]:
        """Every ConnectEventBus stream a lifecycle change on this task
        should publish to — its own stream (for a client watching this
        task specifically) and its target device's stream (for the
        Devices page's live view)."""
        return [f"task:{self.task_id}", f"device:{self.target_device_id}"]


_ROW_COLUMNS = [
    "task_id", "origin", "target_device_id", "action", "payload", "required_capability",
    "status", "result", "error", "last_message", "last_pct", "idempotency_key",
    "context_ref", "handoff_state", "handoff_of", "timeout_seconds", "created_at", "updated_at",
]


def _row_to_task(row: tuple) -> DeviceTask:
    d = dict(zip(_ROW_COLUMNS, row))
    d["payload"] = json.loads(d["payload"] or "{}")
    d["result"] = json.loads(d["result"]) if d["result"] else None
    d["handoff_state"] = json.loads(d["handoff_state"]) if d["handoff_state"] else None
    return DeviceTask(**d)


class DeviceTaskRouter:
    def __init__(self, registry: DeviceRegistry, event_bus: ConnectEventBus):
        self.registry = registry
        self.events = event_bus
        CONNECT_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS device_tasks (
                    task_id TEXT PRIMARY KEY,
                    origin TEXT NOT NULL,
                    target_device_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    required_capability TEXT,
                    status TEXT NOT NULL DEFAULT 'created',
                    result TEXT,
                    error TEXT,
                    last_message TEXT,
                    last_pct INTEGER,
                    idempotency_key TEXT,
                    context_ref TEXT,
                    handoff_state TEXT,
                    handoff_of TEXT,
                    timeout_seconds INTEGER NOT NULL DEFAULT 300,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_device_tasks_idempotency "
                "ON device_tasks (target_device_id, idempotency_key)"
            )
            # Hardening pass: the index above speeds up the SELECT in
            # _find_by_idempotency_key() but never enforced uniqueness —
            # create()'s check-then-insert wasn't atomic, so two concurrent
            # create() calls with the same idempotency_key could both pass
            # the "does one already exist" check before either committed,
            # producing two tasks for one idempotency_key. Confirmed with a
            # real 10-thread race in tests/test_connect_offline.py's
            # test_concurrency before this fix (intermittent — a genuine
            # race, not deterministic — which is why it wasn't already
            # obvious from lighter testing). This partial UNIQUE index
            # closes it at the database level; create()'s except clause
            # below is what makes the *caller* still see the correct
            # (single, existing) task rather than an IntegrityError.
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_device_tasks_idempotency_unique "
                "ON device_tasks (target_device_id, idempotency_key) "
                "WHERE idempotency_key IS NOT NULL"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_device_tasks_target_status "
                "ON device_tasks (target_device_id, status)"
            )
            conn.commit()
        logger.info(f"Device task store DB at {DEVICE_TASKS_DB_PATH}")

    # ─── Lookup ─────────────────────────────────────────────────────────

    def get(self, task_id: str) -> DeviceTask:
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            row = conn.execute(
                f"SELECT {', '.join(_ROW_COLUMNS)} FROM device_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
        if not row:
            raise TaskNotFoundError(task_id)
        return _row_to_task(row)

    def get_pending_for_device(self, device_id: str) -> List[DeviceTask]:
        """Every dispatched/queued task targeting this device, and — as
        a side effect — redelivers anything that was queued_offline
        (flips it to dispatched). Call this from the heartbeat/pending-
        tasks endpoint only, since calling it implies the device is
        online right now (it just authenticated); connect/transports/
        lan_http.py's verify_request already establishes that before
        this is ever reached."""
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_ROW_COLUMNS)} FROM device_tasks "
                f"WHERE target_device_id = ? AND status IN ('dispatched', 'queued_offline') "
                f"ORDER BY created_at ASC",
                (device_id,)
            ).fetchall()
            now = datetime.now().isoformat()
            redelivered_ids = [r[0] for r in rows if r[_ROW_COLUMNS.index("status")] == "queued_offline"]
            if redelivered_ids:
                conn.execute(
                    f"UPDATE device_tasks SET status = 'dispatched', updated_at = ? "
                    f"WHERE task_id IN ({','.join('?' * len(redelivered_ids))})",
                    [now, *redelivered_ids]
                )
                conn.commit()
        tasks = [_row_to_task(r) for r in rows]
        for t in tasks:
            if t.task_id in redelivered_ids:
                t.status = "dispatched"
        return tasks

    # ─── Create / dispatch ──────────────────────────────────────────────

    def create(self, *, origin: str, target_device_id: str, action: str, payload: Optional[Dict] = None,
               required_capability: Optional[str] = None, idempotency_key: Optional[str] = None,
               context_ref: Optional[str] = None, handoff_state: Optional[Dict] = None,
               timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS, handoff_of: Optional[str] = None) -> DeviceTask:
        """Raises UnknownDeviceError if target_device_id isn't a
        currently-trusted device, CapabilityUnavailableError if
        required_capability is set and the device hasn't reported it as
        available+granted. Neither leaves a row behind — a rejected
        create() creates nothing, matching interfaces/api/schemas.py's
        attachment validation failing before a task_store.py row exists."""
        if idempotency_key:
            existing = self._find_by_idempotency_key(target_device_id, idempotency_key)
            if existing:
                logger.info(f"Idempotent create() for key={idempotency_key!r} -> existing task {existing.task_id}")
                return existing

        device = self.registry.get_device_by_external_id(target_device_id, channel=DIRECT_CHANNEL)
        if not device:
            raise UnknownDeviceError(target_device_id)
        if required_capability and not device_supports(device["capabilities"], required_capability):
            raise CapabilityUnavailableError(
                f"device {target_device_id} does not have '{required_capability}' available+granted"
            )

        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        task = DeviceTask(
            task_id=task_id, origin=origin, target_device_id=target_device_id, action=action,
            payload=payload or {}, required_capability=required_capability, status="created",
            idempotency_key=idempotency_key, context_ref=context_ref, handoff_state=handoff_state,
            handoff_of=handoff_of, timeout_seconds=timeout_seconds, created_at=now, updated_at=now,
        )
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            try:
                conn.execute(
                    "INSERT INTO device_tasks (task_id, origin, target_device_id, action, payload, "
                    "required_capability, status, idempotency_key, context_ref, handoff_state, "
                    "handoff_of, timeout_seconds, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (task_id, origin, target_device_id, action, json.dumps(task.payload), required_capability,
                     "created", idempotency_key, context_ref,
                     json.dumps(handoff_state) if handoff_state is not None else None,
                     handoff_of, timeout_seconds, now, now)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                # Lost a genuine race to another create() call with the
                # same (target_device_id, idempotency_key) — the partial
                # UNIQUE index above is what makes this reachable at all.
                # The winner's row is already committed; hand the caller
                # that one instead of a raised IntegrityError, same
                # contract as the early-return check above, and — like
                # that check — no dispatch() call: the winner's own
                # create() call already progresses this task through
                # dispatch(), so re-dispatching here would double-process
                # it (duplicate task.* events, or worse if the winner has
                # already moved it past 'dispatched' by the time we read
                # it back).
                existing = self._find_by_idempotency_key(target_device_id, idempotency_key)
                if existing:
                    logger.info(f"Lost idempotency race for key={idempotency_key!r} "
                                f"-> returning winning task {existing.task_id}")
                    return existing
                raise  # the constraint fired but no row is findable — reraise rather than mask a real bug
        self.events.publish_to(task.streams, "task.created", task_id=task_id, origin=origin,
                                target_device_id=target_device_id, action=action,
                                handoff_of=handoff_of)
        logger.info(f"DeviceTask created: {task_id} ({action} -> {target_device_id})"
                    + (f" [handoff of {handoff_of}]" if handoff_of else ""))
        return self.dispatch(task_id)

    def _find_by_idempotency_key(self, target_device_id: str, idempotency_key: str) -> Optional[DeviceTask]:
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            row = conn.execute(
                f"SELECT {', '.join(_ROW_COLUMNS)} FROM device_tasks "
                f"WHERE target_device_id = ? AND idempotency_key = ? ORDER BY created_at ASC LIMIT 1",
                (target_device_id, idempotency_key)
            ).fetchone()
        return _row_to_task(row) if row else None

    def dispatch(self, task_id: str) -> DeviceTask:
        """Attempts (or re-attempts) delivery based on the target
        device's *current* connection state. Not usually called
        directly — create() calls it once automatically; the heartbeat/
        pending-tasks path is what actually redelivers a queued_offline
        task once the device reconnects (via get_pending_for_device)."""
        task = self.get(task_id)
        device = self.registry.get_device_by_external_id(task.target_device_id, channel=DIRECT_CHANNEL)
        online = bool(device) and device.get("connection_state") == "online"
        new_status = "dispatched" if online else "queued_offline"
        message = "dispatched to device" if online else "device offline — queued for delivery on reconnect"
        self._update(task_id, status=new_status, last_message=message)
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.progress", task_id=task_id, message=message, pct=None)
        return task

    # ─── Device-reported lifecycle ──────────────────────────────────────

    def _check_ownership(self, task: DeviceTask, device_id: str):
        if task.target_device_id != device_id:
            raise TaskNotOwnedByDeviceError(
                f"task {task.task_id} is routed to {task.target_device_id}, not {device_id}"
            )

    def _check_not_terminal(self, task: DeviceTask):
        if task.status in TERMINAL_STATUSES:
            raise InvalidTaskStateError(f"task {task.task_id} is already {task.status}")

    def ack(self, task_id: str, device_id: str) -> DeviceTask:
        task = self.get(task_id)
        self._check_ownership(task, device_id)
        self._check_not_terminal(task)
        self._update(task_id, status="started")
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.started", task_id=task_id, device_id=device_id)
        return task

    def progress(self, task_id: str, device_id: str, message: str, pct: Optional[int] = None) -> DeviceTask:
        task = self.get(task_id)
        self._check_ownership(task, device_id)
        self._check_not_terminal(task)
        self._update(task_id, status="in_progress", last_message=message, last_pct=pct)
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.progress", task_id=task_id, message=message, pct=pct)
        return task

    def action(self, task_id: str, device_id: str, description: str) -> DeviceTask:
        """A discrete action the device took (e.g. "opened Instagram",
        "tapped Send") — SAM Core's own ACT stage, reported from a
        remote device instead of local Hands."""
        task = self.get(task_id)
        self._check_ownership(task, device_id)
        self._check_not_terminal(task)
        self._update(task_id, status="in_progress", last_message=description)
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.action", task_id=task_id, description=description)
        return task

    def verification(self, task_id: str, device_id: str, verified: bool, detail: str = "") -> DeviceTask:
        """The device's own VERIFY-stage report (did the requested state
        actually occur? — same question interfaces/api/ARCHITECTURE.md's
        verification engine asks locally, section 9 of the architecture
        doc). A verification event does not itself complete or fail the
        task — the device still calls complete()/fail() separately —
        this is a signal, not a terminal outcome."""
        task = self.get(task_id)
        self._check_ownership(task, device_id)
        self._check_not_terminal(task)
        self._update(task_id, status="in_progress")
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.verification", task_id=task_id,
                                verified=verified, detail=detail)
        return task

    def complete(self, task_id: str, device_id: str, result: Optional[Dict] = None) -> DeviceTask:
        task = self.get(task_id)
        self._check_ownership(task, device_id)
        self._check_not_terminal(task)
        self._update(task_id, status="completed", result=result or {})
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.completed", task_id=task_id, result=task.result)
        return task

    def fail(self, task_id: str, device_id: str, error: str) -> DeviceTask:
        task = self.get(task_id)
        self._check_ownership(task, device_id)
        self._check_not_terminal(task)
        self._update(task_id, status="failed", error=error)
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.failed", task_id=task_id, error=error)
        return task

    # ─── Desktop/Core-initiated lifecycle ───────────────────────────────

    def cancel(self, task_id: str, reason: Optional[str] = None) -> bool:
        """Unlike ack/progress/action/verification/complete/fail, this
        is called by the *initiator* (desktop/Core), not the device — no
        device_id ownership check. Returns False (not an error) if the
        task was already terminal; a cancel racing a completion is a
        normal outcome, not a bug."""
        task = self.get(task_id)
        if task.status in TERMINAL_STATUSES:
            return False
        self._update(task_id, status="cancelled", error=reason or "cancelled")
        task = self.get(task_id)
        self.events.publish_to(task.streams, "task.cancelled", task_id=task_id, reason=reason)
        return True

    def sweep_timeouts(self, now: Optional[datetime] = None) -> List[DeviceTask]:
        """Fails out any non-terminal task whose updated_at is older
        than its own timeout_seconds. Publishes task.failed (not a
        distinct event type — see module docstring's lifecycle diagram;
        the *status* 'timed_out' is what distinguishes this from an
        ordinary device-reported failure on GET /api/connect/tasks/{id},
        the event itself doesn't need a fifth terminal type)."""
        now = now or datetime.now()
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            rows = conn.execute(
                f"SELECT {', '.join(_ROW_COLUMNS)} FROM device_tasks "
                f"WHERE status NOT IN ({','.join('?' * len(TERMINAL_STATUSES))})",
                list(TERMINAL_STATUSES)
            ).fetchall()
        timed_out = []
        for row in rows:
            task = _row_to_task(row)
            updated = datetime.fromisoformat(task.updated_at)
            if now - updated > timedelta(seconds=task.timeout_seconds):
                self._update(task.task_id, status="timed_out",
                              error=f"No update from device within {task.timeout_seconds}s")
                task = self.get(task.task_id)
                self.events.publish_to(task.streams, "task.failed", task_id=task.task_id, error=task.error)
                timed_out.append(task)
        if timed_out:
            logger.info(f"{len(timed_out)} device task(s) swept to timed_out")
        return timed_out

    # ─── Context handoff ────────────────────────────────────────────────

    def handoff(self, task_id: str, new_target_device_id: str, *, reason: Optional[str] = None) -> DeviceTask:
        """Moves a task's thread to a different device. The *original*
        task_id is cancelled (if not already terminal) — its full event
        history stays exactly where it is, still fetchable via
        GET /api/connect/tasks/{original_task_id}. A *new* DeviceTask is
        created targeting new_target_device_id, with handoff_of pointing
        back — same linkage pattern as interfaces/api/task_store.py's
        retried_from. context_ref and handoff_state carry across
        unchanged: this module never inspects or modifies either, only
        relays them (see module docstring's "not a second memory
        system")."""
        original = self.get(task_id)
        if original.status not in TERMINAL_STATUSES:
            self.cancel(task_id, reason=reason or f"handed off to a new task on {new_target_device_id}")
        new_task = self.create(
            origin=original.target_device_id, target_device_id=new_target_device_id,
            action=original.action, payload=original.payload,
            required_capability=original.required_capability,
            context_ref=original.context_ref, handoff_state=original.handoff_state,
            timeout_seconds=original.timeout_seconds, handoff_of=task_id,
        )
        logger.info(f"Handoff: {task_id} -> {new_task.task_id} (now targeting {new_target_device_id})")
        return new_task

    # ─── Internal ────────────────────────────────────────────────────────

    def _update(self, task_id: str, **fields):
        if not fields:
            return
        fields["updated_at"] = datetime.now().isoformat()
        if "result" in fields and fields["result"] is not None:
            fields["result"] = json.dumps(fields["result"])
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        with sqlite3.connect(DEVICE_TASKS_DB_PATH) as conn:
            conn.execute(f"UPDATE device_tasks SET {set_clause} WHERE task_id = ?",
                         [*fields.values(), task_id])
            conn.commit()
