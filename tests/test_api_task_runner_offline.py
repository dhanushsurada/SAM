"""
Offline test for api/task_runner.py (M8-A).

Unlike tests/test_api_status_model_offline.py, this file imports NO
fastapi — api/task_runner.py is pure Python plus the real engine, so
this test actually runs in a sandbox without fastapi/uvicorn installed
(confirmed: it does, see the run output this was shipped with).

Reuses the exact scripted 6-step scenario, fixtures, and
FakeChromaClient from tests/test_sovereign_e2e_offline.py — the same
proven "165 - 150 = 15" demo path — so this is testing TaskManager
against a scenario already known to work end-to-end through the real
engine, not a new lighter mock invented for this file. Only
Brain.process() and agent.planner.decompose() are mocked, for the same
reason the existing E2E test mocks them: both genuinely require a live
Ollama, which this sandbox doesn't have.

Usage:
    python3 tests/test_api_task_runner_offline.py
"""

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.react_loop import ReactLoop  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.brain import BrainResponse  # noqa: E402
from sovereign.knowledge import VectorIndex  # noqa: E402
from sovereign.security.network_guard import NetworkPolicyViolation  # noqa: E402

from api.task_runner import TaskBusyError, TaskManager  # noqa: E402

results = []
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sovereign"
INSPECTION_REPORT = FIXTURES_DIR / "inspection_report.pdf"
PLANT_SOP = FIXTURES_DIR / "plant_sop.docx"

OFFICIAL_DEMO_TASK = (
    "Review this inspection report against the applicable SOP, identify "
    "the deviations, then calculate the required value, and finally "
    "prepare an approval note with the supporting evidence."
)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _require_fixtures():
    missing = [p for p in (INSPECTION_REPORT, PLANT_SOP) if not p.exists()]
    if missing:
        print("Fixtures missing — run tests/fixtures/sovereign/generate_fixtures.py first:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)


# Same fakes as tests/test_sovereign_e2e_offline.py — duplicated rather
# than imported, matching this repo's convention of self-contained test
# scripts (no test file imports another test file's internals).
class FakeCollection:
    def __init__(self):
        self.ids, self.documents, self.embeddings, self.metadatas = [], [], [], []

    def upsert(self, ids, documents, embeddings, metadatas):
        for i, doc, emb, meta in zip(ids, documents, embeddings, metadatas):
            if i in self.ids:
                idx = self.ids.index(i)
                self.documents[idx], self.embeddings[idx], self.metadatas[idx] = doc, emb, meta
            else:
                self.ids.append(i)
                self.documents.append(doc)
                self.embeddings.append(emb)
                self.metadatas.append(meta)

    def count(self):
        return len(self.ids)

    def query(self, query_embeddings, n_results, include):
        n = min(n_results, len(self.ids))
        distances = [round(0.1 * i, 2) for i in range(n)]
        return {
            "ids": [self.ids[:n]], "documents": [self.documents[:n]],
            "metadatas": [self.metadatas[:n]], "distances": [distances],
        }


class FakeChromaClient:
    def __init__(self):
        self._collections = {}

    def get_or_create_collection(self, name, metadata=None):
        if name not in self._collections:
            self._collections[name] = FakeCollection()
        return self._collections[name]


class FakeIdentity:
    """Stands in for memory.identity.Identity — TaskManager only ever
    calls .load(), so that's all this needs. Keeps this test hermetic
    (no touching the real ~/.sam_data)."""
    def load(self):
        return {"assistant_name": "VEDA"}


def _scripted_responses():
    return {
        0: BrainResponse(text="Reading the inspection report.", action="read_document",
                          action_payload={"path": str(INSPECTION_REPORT)}, raw=""),
        1: BrainResponse(text="Reading the applicable SOP.", action="read_document",
                          action_payload={"path": str(PLANT_SOP)}, raw=""),
        2: BrainResponse(text="Finding the specific pressure limit.", action="search_knowledge",
                          action_payload={"query": "maximum allowed pressure"}, raw=""),
        3: BrainResponse(text="Calculating the deviation.", action="calculate",
                          action_payload={"expression": "165 - 150"}, raw=""),
        4: BrainResponse(text="Preparing the approval note.", action="create_document", action_payload={
            "title": "Approval Note - Boiler Unit B-12",
            "source_documents": ["inspection_report.pdf", "plant_sop.docx"],
            "sections": [
                {"heading": "Executive Summary", "body": "Boiler Unit B-12 was inspected; pressure exceeds SOP maximum."},
                {"heading": "Findings", "body": "Measured pressure was 165 PSI against an allowed maximum of 150 PSI.",
                 "evidence": [
                     {"source": "inspection_report.pdf", "location": "page 1", "text": "Measured pressure: 165 PSI"},
                     {"source": "plant_sop.docx", "location": "Pressure Limits", "text": "Maximum allowed operating pressure is 150 PSI."},
                 ]},
                {"heading": "Deviations", "body": "Pressure exceeds the allowed maximum by 15 PSI."},
                {"heading": "Calculation / Result", "body": "165 - 150 = 15 PSI over the allowed limit."},
                {"heading": "Recommendation", "body": "Do not return to service until confirmed within limits."},
                {"heading": "Verification Status", "body": "All workflow steps completed successfully."},
            ],
        }, raw=""),
        5: BrainResponse(text="Review complete — the approval note has been prepared.", action=None, action_payload=None, raw=""),
    }


def _make_manager(settings):
    loop = ReactLoop(settings)
    loop._knowledge_index = VectorIndex(settings, client=FakeChromaClient())  # M6 Section 23 fallback
    mock_brain = MagicMock()
    return TaskManager(settings, FakeIdentity(), mock_brain, loop), mock_brain


# ─── full lifecycle through the real engine, sovereign mode on ────────────

def test_full_task_lifecycle_matches_the_proven_e2e_scenario():
    _require_fixtures()
    settings = Settings()
    settings.sovereign_mode = True
    settings.sovereign_output_dir = str(Path(tempfile.mkdtemp()) / "output")
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")

    manager, mock_brain = _make_manager(settings)
    scripted = _scripted_responses()
    attack_outcome = {"blocked": None}
    call_sequence = [scripted[0], scripted[1], scripted[2], None, scripted[4], scripted[5]]  # None = the attack slot

    def _brain_side_effect(session):
        idx = mock_brain.process.call_count - 1
        if call_sequence[idx] is None:
            try:
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 80))
                attack_outcome["blocked"] = False
            except NetworkPolicyViolation:
                attack_outcome["blocked"] = True
            except OSError:
                attack_outcome["blocked"] = False
            return scripted[3]
        return call_sequence[idx]

    mock_brain.process.side_effect = _brain_side_effect
    fake_plan = [{"step": i + 1, "description": scripted[i].text} for i in range(6)]

    with patch("agent.planner.decompose", return_value=fake_plan):
        with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
            record = manager.start_task(OFFICIAL_DEMO_TASK)
            check("start_task returns a record with an id", bool(record.id))
            check("status starts at queued or running", record.status in ("queued", "running"))

            deadline = time.time() + 10
            while manager.get_task(record.id).status in ("queued", "running") and time.time() < deadline:
                time.sleep(0.05)

    final = manager.get_task(record.id)
    check("task reached a terminal status within the timeout", final.status in ("completed", "incomplete", "failed"))
    check("task completed (not incomplete/failed)", final.status == "completed")
    check("6 activity steps were captured via on_step", len(final.steps) == 6)
    check("step actions were captured in the real execution order",
          [s.action for s in final.steps] == ["read_document", "read_document", "search_knowledge",
                                               "calculate", "create_document", None])
    check("the calculate step's success flag is True (Verifier passed it)",
          final.steps[3].success is True)
    check("the search_knowledge step got a real adaptive-path-free planner description",
          final.steps[2].label == scripted[2].text)

    check("sovereignty report was captured", final.sovereignty is not None)
    check("blocked attempt recorded in the captured report", final.sovereignty["blocked_count"] >= 1)
    check("no external transmission recorded", final.sovereignty["external_transmission_count"] == 0)
    check("the injected phone-home attempt was actually blocked", attack_outcome["blocked"] is True)

    check("a deliverable was detected", final.deliverable is not None)
    if final.deliverable:
        deliverable_path = Path(final.deliverable["path"])
        check("the deliverable file genuinely exists on disk", deliverable_path.exists())
        check("deliverable_file_path() resolves to the same real file",
              manager.deliverable_file_path(record.id) == deliverable_path)
        check("sources count matches the real create_document payload (2 source docs)",
              final.deliverable["sources"] == 2)
        check("evidence_count matches the real create_document payload (2 evidence entries)",
              final.deliverable["evidence_count"] == 2)

    # last_task_id must survive completion — this is what lets a client
    # that reloads mid-demo (or right after a task finishes) recover
    # context instead of losing it, unlike _active_task_id which the
    # manager clears once the task is no longer running.
    check("last_task_id still points at this task after it finished",
          manager.last_task_id == record.id)


# ─── serialization / busy behaviour ────────────────────────────────────────

def test_second_task_is_rejected_while_first_is_running():
    settings = Settings()
    manager, mock_brain = _make_manager(settings)

    release = threading.Event()

    def _slow_response(session):
        release.wait(timeout=5)
        return BrainResponse(text="done", action=None, action_payload=None, raw="")

    mock_brain.process.side_effect = _slow_response

    with patch("agent.react_loop.ReactLoop._looks_multi_step", return_value=False):
        record1 = manager.start_task("first task")
        time.sleep(0.1)  # let the background thread actually start and flip to "running"
        check("first task is running", manager.get_task(record1.id).status == "running")

        busy_raised = False
        try:
            manager.start_task("second task")
        except TaskBusyError:
            busy_raised = True
        check("a second task while one is running raises TaskBusyError", busy_raised)

        release.set()
        deadline = time.time() + 5
        while manager.get_task(record1.id).status == "running" and time.time() < deadline:
            time.sleep(0.02)
        check("first task finished after being released", manager.get_task(record1.id).status != "running")

        record3 = manager.start_task("third task, after the first finished")
        check("a new task is accepted once the previous one has finished", record3.id != record1.id)
        release.set()  # in case the second mocked call also blocks


def test_empty_task_text_is_rejected():
    settings = Settings()
    manager, _ = _make_manager(settings)
    raised = False
    try:
        manager.start_task("   ")
    except ValueError:
        raised = True
    check("empty/whitespace-only task text raises ValueError", raised)


# ─── status classification (pure unit test, no engine execution) ─────────

def test_status_classification_recognizes_only_known_incomplete_outcomes():
    check("a normal result is 'completed'",
          TaskManager._classify_status("The approval note has been prepared.") == "completed")
    check("'Stopped.' (cancellation) is 'incomplete'",
          TaskManager._classify_status("Stopped.") == "incomplete")
    check("stagnation message is 'incomplete'",
          TaskManager._classify_status("I got stuck repeating the same result ('x') without making progress.") == "incomplete")
    check("max-steps message is 'incomplete'",
          TaskManager._classify_status("I ran out of steps before completing the task. Please try again.") == "incomplete")
    check("a result that merely mentions 'stopped' mid-sentence is NOT misclassified",
          TaskManager._classify_status("The line stopped at the second reading.") == "completed")


if __name__ == "__main__":
    test_full_task_lifecycle_matches_the_proven_e2e_scenario()
    test_second_task_is_rejected_while_first_is_running()
    test_empty_task_text_is_rejected()
    test_status_classification_recognizes_only_known_incomplete_outcomes()

    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} checks passed.")
    if passed != total:
        sys.exit(1)
    print("VEDA API task runner (M8-A) verified against the real engine.")
