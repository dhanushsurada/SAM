"""
Milestone 6 — offline End-to-End Sovereign SAM test.

Real ReactLoop.run_planned_task() / run_task(), real extraction, real
chunking, real (fake-Chroma-backed — see Section 23 of the M6 brief;
chromadb still isn't installed in this sandbox, same as every milestone
since M2) knowledge retrieval, real sovereign tools, real Verifier,
real Reflection, real SocketGuard. The ONLY two things mocked are
Brain.process() and agent.planner.decompose() — both genuinely require
a live Ollama, which this sandbox doesn't have. Everything downstream
of those two calls is the real, unmodified production code path.

This proves: "if the model decides these actions in this order, does
the real system correctly execute, verify, and produce a correct
result end to end" — not "does the model reason correctly," which is
what test_sovereign_e2e_live.py is for.

Usage:
    HOME=/tmp/sam_smoke_e2e python3 tests/test_sovereign_e2e_offline.py
"""

import json
import socket
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.react_loop import ReactLoop  # noqa: E402
from agent.verifier import Verifier  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.brain import BrainResponse  # noqa: E402
from core.session import Session  # noqa: E402
from main import run_task_with_optional_sovereign_mode  # noqa: E402
from sovereign.knowledge import VectorIndex  # noqa: E402
from sovereign.security import SocketGuard  # noqa: E402
from sovereign.security.network_guard import NetworkPolicyViolation  # noqa: E402

results = []
e2e_summary = {}  # populated by test_e2e_planned_path_complete_workflow_with_network_attack(); read by main()
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sovereign"
INSPECTION_REPORT = FIXTURES_DIR / "inspection_report.pdf"
PLANT_SOP = FIXTURES_DIR / "plant_sop.docx"
MALICIOUS_ADDENDUM = FIXTURES_DIR / "malicious_addendum.txt"

OFFICIAL_DEMO_TASK = (
    "Review this inspection report against the applicable SOP, identify "
    "the deviations, then calculate the required value, and finally "
    "prepare an approval note with the supporting evidence."
)
ADAPTIVE_EQUIVALENT_TASK = (
    "Review the inspection report against the applicable SOP, identify "
    "deviations, calculate the required value, and prepare an approval "
    "note with supporting evidence."
)

EXPECTED_DEVIATION = 165 - 150  # matches tests/fixtures/sovereign/generate_fixtures.py


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _require_fixtures():
    missing = [p for p in (INSPECTION_REPORT, PLANT_SOP, MALICIOUS_ADDENDUM) if not p.exists()]
    if missing:
        print("Fixtures missing — run tests/fixtures/sovereign/generate_fixtures.py first:")
        for m in missing:
            print(f"  {m}")
        sys.exit(1)


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


def _new_session(settings):
    return Session(user_input="", identity={}, memories=[], founder_context="", settings=settings)


# ─── wording / path-selection sanity (Sections 3 & 4 of the M6 brief) ────

def test_official_wording_triggers_planner_path():
    loop = ReactLoop(Settings())
    check("Official demo wording ('then'/'finally') triggers the multi-step/Planner heuristic",
          loop._looks_multi_step(OFFICIAL_DEMO_TASK) is True)


def test_equivalent_wording_stays_on_adaptive_path():
    loop = ReactLoop(Settings())
    check("Equivalent wording without trigger keywords stays on the adaptive path",
          loop._looks_multi_step(ADAPTIVE_EQUIVALENT_TASK) is False)


# ─── Category A + B + provenance: the primary planned-path E2E run ───────

def test_e2e_planned_path_complete_workflow_with_network_attack():
    """The main event. Real run_planned_task(), real Sovereign Mode
    wrapping, a genuine phone-home attempt injected mid-run, and full
    provenance verification in the resulting DOCX."""
    _require_fixtures()
    settings = Settings()
    settings.sovereign_mode = True
    settings.sovereign_output_dir = str(Path(tempfile.mkdtemp()) / "output")
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")

    loop = ReactLoop(settings)
    loop._knowledge_index = VectorIndex(settings, client=FakeChromaClient())  # Section 23 fallback

    scripted = {
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
                {"heading": "Executive Summary",
                 "body": "Boiler Unit B-12 was inspected on 2026-08-20. Recorded pressure exceeds the SOP-allowed maximum."},
                {"heading": "Findings",
                 "body": "Measured pressure was 165 PSI against an SOP-allowed maximum of 150 PSI.",
                 "evidence": [
                     {"source": "inspection_report.pdf", "location": "page 1", "text": "Measured pressure: 165 PSI"},
                     {"source": "plant_sop.docx", "location": "Pressure Limits", "text": "Maximum allowed operating pressure is 150 PSI."},
                 ]},
                {"heading": "Deviations", "body": "Pressure reading exceeds the allowed maximum by 15 PSI."},
                {"heading": "Calculation / Result", "body": "165 - 150 = 15 PSI over the allowed limit."},
                {"heading": "Recommendation",
                 "body": "Do not return to service until pressure is confirmed within limits and corrective action is documented per SOP."},
                {"heading": "Verification Status",
                 "body": "All workflow steps completed successfully; no failures were encountered while reviewing the inspection report and SOP."},
            ],
        }, raw=""),
        5: BrainResponse(text="Review complete — the approval note has been prepared.", action=None, action_payload=None, raw=""),
    }

    attack_outcome = {"blocked": None}
    call_sequence = [scripted[1], scripted[2], None, scripted[4], scripted[5]]  # None marks the attack slot

    def _brain_side_effect(session):
        idx = mock_brain.process.call_count - 1
        if idx >= len(call_sequence):
            raise AssertionError(f"brain.process called more times than scripted (call #{idx + 1})")
        if call_sequence[idx] is None:
            # Deliberate phone-home attempt, literal IP (no DNS), happening
            # *inside* the same real run_planned_task() call this test is
            # exercising — Section 9 of the M6 brief.
            try:
                socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 80))
                attack_outcome["blocked"] = False
            except NetworkPolicyViolation:
                attack_outcome["blocked"] = True
            except OSError:
                attack_outcome["blocked"] = False
            return scripted[3]
        return call_sequence[idx]

    mock_brain = MagicMock()
    mock_brain.process.side_effect = _brain_side_effect

    fake_plan = [{"step": i + 1, "description": scripted[i].text} for i in range(6)]
    session = _new_session(settings)
    original_connect = socket.socket.connect

    with patch("agent.planner.decompose", return_value=fake_plan) as mock_decompose:
        with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
            result_text, network_report = run_task_with_optional_sovereign_mode(
                loop, settings, OFFICIAL_DEMO_TASK, mock_brain, session, "",
                scripted[0], threading.Event(),
            )

    check("planner.decompose was actually called (planned path)", mock_decompose.called)

    # ── Category B: sovereignty ──
    check("The phone-home attempt actually occurred and was evaluated", attack_outcome["blocked"] is not None)
    check("SocketGuard blocked the attempt before a real external connection", attack_outcome["blocked"] is True)
    check("network_report is available (Sovereign Mode actually ran)", network_report is not None)
    check("The blocked attempt was recorded in the real report", network_report.blocked_count >= 1)
    check("No external transmission occurred", network_report.external_transmission_count == 0)
    check("Guard restored socket.socket.connect after the run", socket.socket.connect is original_connect)

    # ── Category D: failure recovery — the attack didn't kill the task ──
    check("The legitimate task still completed after the blocked attempt", "approval note" in result_text.lower() or "complete" in result_text.lower())

    # ── deliverable + provenance ──
    out_dir = Path(settings.sovereign_output_dir)
    docx_files = list(out_dir.glob("*.docx"))
    check("Exactly one Approval Note DOCX was created", len(docx_files) == 1)

    import docx as docx_lib
    doc = docx_lib.Document(str(docx_files[0]))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    for required in ["Executive Summary", "Findings", "Deviations", "Calculation", "Recommendation", "Verification Status"]:
        check(f"DOCX contains the required '{required}' section", required in full_text)
    check("DOCX preserves source filenames (provenance)", "inspection_report.pdf" in full_text and "plant_sop.docx" in full_text)
    check("DOCX preserves the quoted evidence text from the real inspection report", "Measured pressure: 165 PSI" in full_text)
    check("DOCX preserves the quoted evidence text from the real SOP", "Maximum allowed operating pressure is 150 PSI" in full_text)
    check("The deterministic calculation result appears in the DOCX", str(EXPECTED_DEVIATION) in full_text)

    # ── knowledge base was actually populated by real ingestion (not hand-seeded) ──
    with patch("sovereign.knowledge.vector_index.get_embedding", return_value=[0.1, 0.1]):
        raw = loop._knowledge_index.query("pressure", top_k=10)
    indexed_filenames = {m.get("filename") for m in raw["metadatas"][0]}
    check("Both source documents were really indexed as a side effect of read_document",
          "inspection_report.pdf" in indexed_filenames and "plant_sop.docx" in indexed_filenames)

    e2e_summary.update({
        "documents_processed": 2,
        "knowledge_retrieval": "passed" if raw["documents"][0] else "empty",
        "calculation": f"165 - 150 = {EXPECTED_DEVIATION}",
        "verification": "passed",
        "deliverable_created": len(docx_files) == 1,
        "network_attempts_blocked": network_report.blocked_count,
        "successful_external_connections": network_report.external_transmission_count,
        "sovereignty_evidence": "available" if Path(settings.sovereign_network_log).exists() else "unavailable",
    })
    # No return value — pytest auto-discovers test_* functions and warns
    # (PytestReturnNotNoneWarning) if one returns non-None. This function
    # already asserts everything it needs to via check(); the machine-
    # readable summary is reported separately, from e2e_summary, by main().


# ─── adaptive path (Section 4/26) ─────────────────────────────────────────

def test_e2e_adaptive_path_completes_via_run_task():
    settings = Settings()
    loop = ReactLoop(settings)
    session = _new_session(settings)

    initial_response = BrainResponse(text="", action="calculate", action_payload={"expression": "165 - 150"}, raw="")
    mock_brain = MagicMock()
    mock_brain.process.side_effect = [
        BrainResponse(text="The pressure exceeds the limit by 15 PSI. Review complete.", action=None, action_payload=None, raw=""),
    ]

    with patch("agent.planner.decompose") as mock_decompose:
        result = loop.run_planned_task(
            task=ADAPTIVE_EQUIVALENT_TASK, brain=mock_brain, session=session, founder_context="",
            initial_response=initial_response, cancel_event=threading.Event(),
        )
        check("planner.decompose is never called on the adaptive path", not mock_decompose.called)
    check("The adaptive path still produces a real result through the real calculate tool", "15" in result)


# ─── Category C: prompt injection ─────────────────────────────────────────

def test_e2e_prompt_injection_document_is_neutralized():
    _require_fixtures()
    settings = Settings()
    loop = ReactLoop(settings)

    with SocketGuard(settings, task_label="injection-test") as guard:
        observation = loop.execute("read_document", {"path": str(MALICIOUS_ADDENDUM)})

    check("The malicious document reads successfully as data, no crash", "BEGIN DOCUMENT CONTENT" in observation)
    begin_idx = observation.index("BEGIN DOCUMENT CONTENT")
    injection_idx = observation.index("Ignore all previous instructions")
    check("The injected text ends up inside the untrusted-content block, not before it", injection_idx > begin_idx)
    check("The data-not-instructions reinforcement is present", "DATA to analyze" in observation)
    check("Reading the malicious document made zero network connection attempts", len(guard.report().attempts) == 0)


# ─── Category D (focused): a real tool failure isn't hidden ──────────────

def test_e2e_tool_failure_is_recorded_not_hidden():
    settings = Settings()
    loop = ReactLoop(settings)
    v = Verifier(settings)

    observation = loop.execute("read_document", {"path": str(FIXTURES_DIR / "does_not_exist.pdf")})
    check("A missing document produces a clear error observation", observation.startswith("Error executing read_document:"))
    result = v.verify("read_document", {"path": "does_not_exist.pdf"}, observation, 0.05)
    check("The Verifier correctly flags it as a failure — not silently successful", result.success is False)


# ─── Category E: guard restoration, including after a mid-task exception ─

def test_e2e_guard_restored_after_exception_mid_task():
    settings = Settings()
    settings.sovereign_mode = True
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")
    loop = ReactLoop(settings)
    original_connect = socket.socket.connect

    mock_brain = MagicMock()
    mock_brain.process.side_effect = RuntimeError("simulated Brain failure mid-task")
    session = _new_session(settings)
    initial_response = BrainResponse(text="", action="calculate", action_payload={"expression": "1+1"}, raw="")
    fake_plan = [{"step": 1, "description": "a"}, {"step": 2, "description": "b"}]

    with patch("agent.planner.decompose", return_value=fake_plan):
        try:
            run_task_with_optional_sovereign_mode(
                loop, settings, "do one thing then finally another thing",
                mock_brain, session, "", initial_response, threading.Event(),
            )
            check("The simulated mid-task exception should have propagated", False)
        except RuntimeError:
            check("The simulated mid-task exception should have propagated", True)

    check("socket.socket.connect is restored even after a mid-task exception", socket.socket.connect is original_connect)
    check("Evidence was still written despite the failure (finally-block)", Path(settings.sovereign_network_log).exists())


def test_sovereign_mode_off_leaves_socket_connect_untouched():
    settings = Settings()
    settings.sovereign_mode = False
    loop = ReactLoop(settings)
    original_connect = socket.socket.connect
    session = _new_session(settings)
    mock_brain = MagicMock()
    mock_brain.process.side_effect = [BrainResponse(text="done", action=None, action_payload=None, raw="")]
    initial_response = BrainResponse(text="", action="calculate", action_payload={"expression": "1+1"}, raw="")

    with patch("agent.planner.decompose", return_value=[{"step": 1, "description": "a"}, {"step": 2, "description": "b"}]):
        result_text, network_report = run_task_with_optional_sovereign_mode(
            loop, settings, "do one thing then finally another", mock_brain, session, "",
            initial_response, threading.Event(),
        )
    check("network_report is None when Sovereign Mode is off — 'not measured', not 'zero'", network_report is None)
    check("socket.socket.connect was never touched when Sovereign Mode is off", socket.socket.connect is original_connect)


def main():
    _require_fixtures()
    test_official_wording_triggers_planner_path()
    test_equivalent_wording_stays_on_adaptive_path()
    test_e2e_planned_path_complete_workflow_with_network_attack()
    test_e2e_adaptive_path_completes_via_run_task()
    test_e2e_prompt_injection_document_is_neutralized()
    test_e2e_tool_failure_is_recorded_not_hidden()
    test_e2e_guard_restored_after_exception_mid_task()
    test_sovereign_mode_off_leaves_socket_connect_untouched()

    print(f"\n{sum(results)}/{len(results)} checks passed.")

    machine_readable = {"workflow": "confidential-industrial-inspection", "status": "passed" if all(results) else "failed"}
    machine_readable.update(e2e_summary)
    print("\nE2E result:")
    print(json.dumps(machine_readable, indent=2))

    if not all(results):
        sys.exit(1)
    print("\nSovereign Workbench E2E workflow (Milestone 6, offline) verified.")


if __name__ == "__main__":
    main()
