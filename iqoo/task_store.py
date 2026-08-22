"""
iQOO — Task Store (Phase 1)

Bookkeeping for competition tasks submitted from the phone: status,
instruction, timestamps, result, and per-task cancellation signals.

This is deliberately NOT the same thing as memory/store.py (ChromaDB +
SQLite AI memory) or founder_mode's store. Those hold what SAM has
learned; this holds what SAM is currently doing. Mirrors the "Local Data
Separation" principle already used by ecosystem/device_registry.py: task
bookkeeping and AI memory are kept apart even though both live locally.

Stored at ~/.sam_data/iqoo/tasks.db — same base directory convention as
every other SAM subsystem.
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

# Full state machine per the PDR (section 8.5). "queued" is this store's
# own pre-state before the worker thread picks a task up, layered on top
# of the PDR's "received" event which fires the moment the row is created.
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ALL_STATUSES = {
    "queued", "received", "understanding", "planning", "executing",
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
            conn.commit()
        logger.info(f"iQOO task store DB at {TASKS_DB_PATH}")

    # ─── Create / Read ──────────────────────────────────────────────────

    def create_task(self, instruction: str, input_type: str = "text",
                     attachments: Optional[List[Dict]] = None) -> str:
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO tasks (task_id, instruction, input_type, attachments, "
                "status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (task_id, instruction, input_type, json.dumps(attachments or []),
                 "queued", now, now)
            )
            conn.commit()
        logger.info(f"Task created: {task_id} ({input_type})")
        return task_id

    def get_task(self, task_id: str) -> Optional[Dict]:
        with sqlite3.connect(TASKS_DB_PATH) as conn:
            row = conn.execute(
                "SELECT task_id, instruction, input_type, attachments, status, "
                "result_text, error, cancel_requested, created_at, updated_at "
                "FROM tasks WHERE task_id = ?",
                (task_id,)
            ).fetchone()
        if not row:
            return None
        cols = ["task_id", "instruction", "input_type", "attachments", "status",
                "result_text", "error", "cancel_requested", "created_at", "updated_at"]
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

    @staticmethod
    def db_path() -> Path:
        return TASKS_DB_PATH
