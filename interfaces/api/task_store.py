"""
SAM Interfaces — API — Task Store (Phase 1, extended in Phase 3A)

(Moved here in Phase 3A.5 — originated as iqoo/task_store.py. This is
the phone-task HTTP+SSE interface's own task ledger, not a reusable
component other interfaces share; iqoo/task_store.py now forwards here
for backward compatibility.)

Bookkeeping for competition tasks submitted from the phone: status,
instruction, timestamps, result, and per-task cancellation signals.

This is deliberately NOT the same thing as memory/store.py (ChromaDB +
SQLite AI memory) or founder_mode's store. Those hold what SAM has
learned; this holds what SAM is currently doing. Mirrors the "Local Data
Separation" principle already used by connect/core/device_registry.py: task
bookkeeping and AI memory are kept apart even though both live locally.
This class never imports or touches memory/ or founder_mode/ in any way
— reset_demo_state() below can only ever delete rows in this file's own
tasks table.

Stored at ~/.sam_data/iqoo/tasks.db — same base directory convention as
every other SAM subsystem. NOTE: the on-disk folder is deliberately still
named "iqoo" (IQOO_DIR below) even after this code moved to interfaces/api/
— it's a literal string, independent of the Python package path, kept
unchanged so no data migration is required for existing installs.

Phase 3A additions: a `retried_from` column (retry history/debugging),
recover_orphaned_tasks() (server-restart reliability), and
reset_demo_state() (controlled demo reset).
"""

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger("SAM.iQOO.TaskStore")

SAM_DATA_DIR = Path.home() / ".sam_data"
IQOO_DIR = SAM_DATA_DIR / "iqoo"
TASKS_DB_PATH = IQOO_DIR / "tasks.db"

ORPHAN_ERROR_MESSAGE = "Orphaned by a server restart — no worker was left to finish this task."

# Full state machine per the PDR (section 8.5), extended in Phase 2 with
# "perceiving" for image/audio interpretation. "queued" is this store's
# own pre-state before the worker thread picks a task up, layered on top
# of the PDR's "received" event which fires the moment the row is created.
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ALL_STATUSES = {
    "queued", "received", "understanding", "perceiving", "planning", "executing",
    "testing", "verifying", *TERMINAL_STATUSES,
}


class TaskStore:
    def __init__(self):
        IQOO_DIR.mkdir(parents=True, exist_ok=True)
        self._cancel_events: Dict[str, threading.Event] = {}
        self._cancel_lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    instruction TEXT NOT NULL,
                    input_type TEXT NOT NULL DEFAULT 'text',
                    attachments TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'queued',
                    result_text TEXT,
                    error TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            # Phase 3A: additive column for pre-existing Phase 1/2
            # databases that predate it. SQLite has no "ADD COLUMN IF
            # NOT EXISTS", so the standard lightweight-migration pattern
            # is to attempt it and swallow the "duplicate column" error.
            try:
                conn.execute("ALTER TABLE tasks ADD COLUMN retried_from TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            conn.commit()
        logger.info(f"iQOO task store DB at {TASKS_DB_PATH}")

    # ─── Create / Read ──────────────────────────────────────────────────

    def create_task(self, instruction: str, input_type: str = "text",
                     attachments: Optional[List[Dict]] = None,
                     retried_from: Optional[str] = None) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, instruction, input_type, attachments, "
                "status, created_at, updated_at, retried_from) VALUES (?,?,?,?,?,?,?,?)",
                (task_id, instruction, input_type, json.dumps(attachments or []),
                 "queued", now, now, retried_from)
            )
            conn.commit()
        logger.info(f"Task created: {task_id} ({input_type})" +
                    (f" [retry of {retried_from}]" if retried_from else ""))
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            row = conn.execute(
                "SELECT task_id, instruction, input_type, attachments, status, "
                "result_text, error, cancel_requested, created_at, updated_at, retried_from "
                "FROM tasks WHERE task_id = ?",
                (task_id,)
            ).fetchone()
        if not row:
            return None
        cols = ["task_id", "instruction", "input_type", "attachments", "status",
                "result_text", "error", "cancel_requested", "created_at", "updated_at",
                "retried_from"]
        record = dict(zip(cols, row))
        record["attachments"] = json.loads(record["attachments"])
        record["cancel_requested"] = bool(record["cancel_requested"])
        return record

    def list_tasks(self, limit: int = 50) -> List[Dict]:
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            rows = conn.execute(
                "SELECT task_id, instruction, status, created_at, updated_at "
                "FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        cols = ["task_id", "instruction", "status", "created_at", "updated_at"]
        return [dict(zip(cols, r)) for r in rows]

    # ─── Update ─────────────────────────────────────────────────────────

    def update_status(self, task_id: str, status: str, result_text: Optional[str] = None,
                       error: Optional[str] = None):
        if status not in ALL_STATUSES:
            logger.warning(f"Unknown status '{status}' for task {task_id} — recording anyway")

        # Phase 3A: once a task reaches a terminal status, it stays
        # there — no further write can move it, including a legitimate
        # in-flight status update from a thread that was already
        # abandoned by a timeout (see TaskGateway._run_task_with_timeout).
        # Without this guard, an orphaned thread finishing late could
        # silently flip a task the phone was already told "failed
        # (timeout)" about back to "completed" or "cancelled" minutes
        # later, which is a worse and more confusing outcome than simply
        # ignoring the late write.
        current = self.get_task(task_id)
        if current and current["status"] in TERMINAL_STATUSES:
            logger.debug(
                f"Ignoring status update to '{status}' for task {task_id} — "
                f"already terminal ({current['status']})")
            return

        now = datetime.now().isoformat()
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            if result_text is not None and error is not None:
                conn.execute(
                    "UPDATE tasks SET status=?, result_text=?, error=?, updated_at=? WHERE task_id=?",
                    (status, result_text, error, now, task_id))
            elif result_text is not None:
                conn.execute(
                    "UPDATE tasks SET status=?, result_text=?, updated_at=? WHERE task_id=?",
                    (status, result_text, now, task_id))
            elif error is not None:
                conn.execute(
                    "UPDATE tasks SET status=?, error=?, updated_at=? WHERE task_id=?",
                    (status, error, now, task_id))
            else:
                conn.execute(
                    "UPDATE tasks SET status=?, updated_at=? WHERE task_id=?",
                    (status, now, task_id))
            conn.commit()

    def request_cancel(self, task_id: str) -> bool:
        """Marks cancellation requested and sets the in-memory Event the
        running task's cancel_event checks between steps (real interrupt,
        not just a UI flag — mirrors main.py's _cancel_event mechanism)."""
        record = self.get_task(task_id)
        if not record:
            return False
        if record["status"] in TERMINAL_STATUSES:
            return False  # already finished — nothing to cancel

        with sqlite3.connect(TASKS_DB_PATH) as conn:
            conn.execute(
                "UPDATE tasks SET cancel_requested=1, updated_at=? WHERE task_id=?",
                (datetime.now().isoformat(), task_id)
            )
            conn.commit()
        self.get_cancel_event(task_id).set()
        logger.info(f"Cancellation requested for task {task_id}")
        return True

    def get_cancel_event(self, task_id: str) -> threading.Event:
        with self._cancel_lock:
            if task_id not in self._cancel_events:
                self._cancel_events[task_id] = threading.Event()
            return self._cancel_events[task_id]

    def cleanup_cancel_event(self, task_id: str):
        with self._cancel_lock:
            self._cancel_events.pop(task_id, None)

    # ─── Phase 3A: reliability ──────────────────────────────────────────

    def recover_orphaned_tasks(self) -> List[str]:
        """Called once at TaskGateway startup. Any task left in a
        non-terminal status from a previous process (crash, kill, or a
        clean restart while a task was mid-flight) has no live worker
        thread left that will ever update it again — without this, such
        a task would show as permanently 'executing'/'perceiving'/etc.
        forever, which is worse and more confusing than an honest
        failure. Marks every non-terminal task 'failed' with a
        distinguishable error message so it's never mistaken for a real
        execution failure. Returns the list of recovered task_ids (empty
        on a clean start with nothing left over)."""
        placeholders = ",".join("?" * len(TERMINAL_STATUSES))
        now = datetime.now().isoformat()
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            rows = conn.execute(
                f"SELECT task_id FROM tasks WHERE status NOT IN ({placeholders})",
                tuple(TERMINAL_STATUSES)
            ).fetchall()
            recovered = [r[0] for r in rows]
            if recovered:
                conn.execute(
                    f"UPDATE tasks SET status='failed', error=?, updated_at=? "
                    f"WHERE status NOT IN ({placeholders})",
                    (ORPHAN_ERROR_MESSAGE, now, *TERMINAL_STATUSES)
                )
                conn.commit()
        if recovered:
            logger.warning(f"Recovered {len(recovered)} orphaned task(s) from a previous process: {recovered}")
        return recovered

    def reset_demo_state(self) -> int:
        """Deletes every task row and clears in-memory cancel events.
        Only ever touches this file's own tasks table — never imports or
        references memory/store.py or founder_mode's store, so SAM's
        real long-term memory cannot be affected by this call no matter
        what calls it or how. Returns the number of rows deleted."""
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            cursor = conn.execute("DELETE FROM tasks")
            conn.commit()
            deleted = cursor.rowcount
        with self._cancel_lock:
            self._cancel_events.clear()
        logger.warning(f"Demo reset: deleted {deleted} task row(s)")
        return deleted

    @staticmethod
    def db_path() -> Path:
        return TASKS_DB_PATH
