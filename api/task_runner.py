"""
Task execution + in-memory task store for the VEDA localhost API (M8-A).

No fastapi import — pure Python plus the existing engine
(main.run_task_with_optional_sovereign_mode, core.session.Session).
Exercised directly in tests/test_api_task_runner_offline.py the same
way the repo's own tests exercise ReactLoop, without needing
fastapi/uvicorn installed. api/app.py is the only place HTTP concerns
(status codes, request/response models) get layered on top of this.

Serialization: sovereign/security/network_guard.py's SocketGuard
monkeypatches socket.socket.connect process-wide for the duration of a
guarded run. Two sovereign tasks running concurrently would each
install/restore that patch, and one task's network activity could be
attributed to the other's report — untested, unvalidated territory
(see the M8 audit's risk notes). So only one task may be RUNNING at a
time; a second submission while one is active is rejected with
TaskBusyError rather than queued or run concurrently, per the M8-A
brief ("keep task execution serialized... one active task at a time is
sufficient... do not build an enterprise task queue").
"""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from core.session import Session

logger = logging.getLogger("SAM.API.Tasks")

# react_loop.py's own literal, fixed outcome strings for cancellation /
# stagnation / max-steps (see run_task and run_planned_task). Recognized
# here so the API can report "incomplete" instead of "completed" for
# these three specific real outcomes — not a fabricated success/failure
# classification, since the engine itself doesn't compute one for the
# task as a whole (only per tool-call, via each step's `attempts`).
_KNOWN_INCOMPLETE_PREFIXES = (
    "Stopped.",
    "I got stuck repeating the same result",
    "I ran out of steps before completing the task.",
)


class TaskBusyError(Exception):
    """Raised by TaskManager.start_task() when a task is already running."""


@dataclass
class ActivityStep:
    step: int
    action: Optional[str]
    label: str
    observation: str
    success: Optional[bool]  # None when the step had no tool call to verify (e.g. a plain-text step)


@dataclass
class TaskRecord:
    id: str
    task_text: str
    status: str = "queued"  # queued | running | completed | incomplete | failed
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    steps: List[ActivityStep] = field(default_factory=list)
    result: Optional[str] = None
    error: Optional[str] = None
    sovereignty: Optional[dict] = None  # NetworkGuardReport.to_dict(), or None if sovereign_mode was off
    deliverable: Optional[dict] = None  # {"filename": ..., "path": ...} if a .docx was produced


class TaskManager:
    """One instance lives for the process lifetime (see api/state.py)."""

    def __init__(self, settings, identity, brain, react_loop):
        self.settings = settings
        self.identity = identity
        self.brain = brain
        self.react_loop = react_loop
        self._tasks: Dict[str, TaskRecord] = {}
        self._run_lock = threading.Lock()   # held for the duration of one task's execution
        self._store_lock = threading.Lock()  # guards self._tasks / record field mutation
        self._active_task_id: Optional[str] = None
        # Set once per start_task() call and never cleared (unlike
        # _active_task_id, which resets to None when a task finishes).
        # Purely so a client that reloads mid-demo — or right after a
        # task completes — has something to ask for instead of losing
        # all task context. Exposed read-only via /api/status.
        self._last_task_id: Optional[str] = None

    @property
    def last_task_id(self) -> Optional[str]:
        with self._store_lock:
            return self._last_task_id

    # ─── public API used by api/app.py ─────────────────────────────────

    def start_task(self, task_text: str) -> TaskRecord:
        task_text = (task_text or "").strip()
        if not task_text:
            raise ValueError("Task text is required")

        if not self._run_lock.acquire(blocking=False):
            raise TaskBusyError(
                f"A task is already running (id={self._active_task_id}). "
                "VEDA runs one sovereign task at a time by design — wait "
                "for it to finish, then check its status or submit again."
            )

        record = TaskRecord(id=uuid.uuid4().hex[:12], task_text=task_text)
        with self._store_lock:
            self._tasks[record.id] = record
            self._active_task_id = record.id
            self._last_task_id = record.id

        threading.Thread(target=self._run, args=(record,), daemon=True).start()
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._store_lock:
            return self._tasks.get(task_id)

    def deliverable_file_path(self, task_id: str) -> Optional[Path]:
        record = self.get_task(task_id)
        if record is None or record.deliverable is None:
            return None
        path = Path(record.deliverable["path"])
        return path if path.exists() else None

    # ─── internal ───────────────────────────────────────────────────────

    def _on_step(self, record: TaskRecord, raw_step: dict):
        """Callback passed down into run_task_with_optional_sovereign_mode
        -> ReactLoop.run_task/run_planned_task. raw_step is exactly the
        dict those loops already build internally — nothing here is
        invented, only relabeled for display."""
        try:
            action = raw_step.get("action")
            description = raw_step.get("description")  # present on the planned path only
            if not description:
                description = self._describe(action, raw_step.get("payload") or {})

            attempts = raw_step.get("attempts")
            success = attempts[-1]["success"] if attempts else None

            step = ActivityStep(
                step=raw_step.get("step", len(record.steps) + 1),
                action=action,
                label=description,
                observation=raw_step.get("observation", ""),
                success=success,
            )
            with self._store_lock:
                record.steps.append(step)

            if action == "create_document" and success is not False:
                self._detect_deliverable(record, raw_step.get("payload") or {})
        except Exception as e:
            # A broken display callback must never break the task it's
            # observing — the same defensive stance react_loop.py
            # already takes around its own Reflection call.
            logger.debug(f"on_step display callback failed (task continues): {e}")

    @staticmethod
    def _describe(action: Optional[str], payload: dict) -> str:
        """Adaptive-path fallback label, used only when the Planner
        didn't supply a description (i.e. the task ran through the plain
        ReAct loop, not the planned one). Built solely from data the
        step already returned — the real action name and its real
        payload — not invented."""
        if action == "read_document":
            return f"Read {Path(payload.get('path', '')).name or 'a document'}"
        if action == "search_knowledge":
            return f'Searched local knowledge for "{payload.get("query", "")}"'
        if action == "calculate":
            return f"Calculated {payload.get('expression', '')}"
        if action == "create_document":
            return f'Prepared "{payload.get("title", "a document")}"'
        return action or "Step"

    def _detect_deliverable(self, record: TaskRecord, payload: dict):
        """create_document's tool return value is a human sentence, not
        a structured path. Rather than parse that string, this looks at
        the real output directory — the actual artifact — and picks the
        most recently modified .docx. Correct as long as tasks are
        serialized (guaranteed by this class), so nothing else could be
        writing there concurrently.

        sources/evidence_count come from the real call payload that
        triggered this step (the exact arguments create_document was
        actually invoked with), not from inspecting the generated file —
        counting real inputs rather than re-parsing the tool's output."""
        out_dir = Path(self.settings.sovereign_output_dir)
        if not out_dir.exists():
            return
        docx_files = sorted(out_dir.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not docx_files:
            return
        newest = docx_files[0]
        sections = payload.get("sections") or []
        record.deliverable = {
            "filename": newest.name,
            "path": str(newest),
            "sources": len(payload.get("source_documents") or []),
            "evidence_count": sum(len(s.get("evidence") or []) for s in sections),
        }

    def _run(self, record: TaskRecord):
        # Import here, not at module load: main.py does module-level
        # setup (a logger, etc.) that's only actually needed once a
        # task runs, not merely to import TaskManager for testing its
        # non-execution paths.
        from main import run_task_with_optional_sovereign_mode

        record.status = "running"
        record.started_at = time.time()
        try:
            session = Session(
                user_input=record.task_text,
                identity=self.identity.load(),
                # Deliberately empty: a sovereign document-analysis task
                # is not a personal-assistant conversation. Keeping SIH
                # task sessions out of personal memory/founder context
                # extends the same corpus-separation principle M2
                # already established for sam_memory vs sam_documents
                # to episodic memory as well — not a shortcut, a
                # boundary this API intentionally preserves.
                memories=[],
                founder_context="",
                settings=self.settings,
            )
            result_text, network_report = run_task_with_optional_sovereign_mode(
                self.react_loop, self.settings, record.task_text, self.brain, session,
                founder_context="", initial_response=None, cancel_event=None,
                on_step=lambda raw: self._on_step(record, raw),
            )
            record.result = result_text
            record.sovereignty = network_report.to_dict() if network_report is not None else None
            record.status = self._classify_status(result_text)
        except Exception as e:
            logger.error(f"Task {record.id} failed: {e}", exc_info=True)
            record.error = str(e)
            record.status = "failed"
        finally:
            record.completed_at = time.time()
            with self._store_lock:
                self._active_task_id = None
            self._run_lock.release()

    @staticmethod
    def _classify_status(result_text: str) -> str:
        """"incomplete" for react_loop.py's three known non-success exit
        strings (cancellation / stagnation / max-steps — see the module
        docstring), "completed" for everything else. Not a fabricated
        pass/fail verdict: the engine itself only judges success per
        tool call (each step's `attempts`), never for a task overall, so
        this only recognizes the engine's own literal defined outcomes
        rather than inventing a new classification on top of them."""
        return "incomplete" if any(result_text.startswith(p) for p in _KNOWN_INCOMPLETE_PREFIXES) else "completed"
