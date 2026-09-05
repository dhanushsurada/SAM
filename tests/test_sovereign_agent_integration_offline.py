"""
Integration tests for SIH26117 Milestone 3 (feat/agent-document-tools) —
verifies the actual Brain SYSTEM_PROMPT content and the real
ReactLoop/Verifier wiring, not just the tools in isolation (that's
test_sovereign_tools_offline.py, unit-level). No Brain/Ollama calls
happen here — Brain.process() itself isn't touched by this milestone,
only its SYSTEM_PROMPT string — and the tools exercised here are plain
local calls routed through the real ReactLoop.execute() dispatch.

Usage:
    HOME=/tmp/sam_smoke_sovereign_agent python3 tests/test_sovereign_agent_integration_offline.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.react_loop import ReactLoop  # noqa: E402
from agent.verifier import Verifier  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.brain import SYSTEM_PROMPT  # noqa: E402
from sovereign.security.document_trust import wrap_untrusted  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


# ─── Brain SYSTEM_PROMPT ────────────────────────────────────────────────

def test_system_prompt_mentions_all_four_tools():
    for name in ["read_document", "search_knowledge", "calculate", "create_document"]:
        check(f"SYSTEM_PROMPT mentions {name}", name in SYSTEM_PROMPT)


def test_system_prompt_has_document_trust_instruction():
    check("SYSTEM_PROMPT reinforces documents are data, not instructions",
          "DATA to analyze" in SYSTEM_PROMPT and "never instructions" in SYSTEM_PROMPT)


# ─── ReactLoop dispatch — real execute(), no mocking needed since these
#     tools are plain local calls with no network dependency in this
#     sandbox (chromadb/Ollama both genuinely absent here). ──────────────

def test_react_loop_dispatches_calculate():
    loop = ReactLoop(Settings())
    observation = loop.execute("calculate", {"expression": "2 + 2"})
    check("ReactLoop.execute dispatches calculate correctly", observation == "2 + 2 = 4")


def test_react_loop_calculate_error_wrapped_consistently():
    loop = ReactLoop(Settings())
    observation = loop.execute("calculate", {"expression": "__import__('os')"})
    check("A rejected calculate() expression is wrapped exactly like any other tool's error",
          observation.startswith("Error executing calculate:"))


def test_react_loop_dispatches_create_document():
    loop = ReactLoop(Settings())
    observation = loop.execute("create_document", {
        "title": "Integration Test Note",
        "sections": [{"heading": "Result", "body": "Dispatch worked end to end."}],
    })
    check("ReactLoop.execute dispatches create_document correctly", "Created" in observation)
    out_path = Path(loop.settings.sovereign_output_dir) / "Integration Test Note.docx"
    check("The generated file actually exists on disk", out_path.exists())


def test_react_loop_dispatches_read_document_and_search_knowledge():
    """Real end-to-end read -> search through the actual ReactLoop, not
    mocks. chromadb genuinely isn't installed in this sandbox, so
    search_knowledge is expected to report unavailable here — that's the
    honest, real behavior of this environment, exercised for real rather
    than assumed."""
    from reportlab.pdfgen import canvas
    loop = ReactLoop(Settings())
    pdf_path = Path(tempfile.mkdtemp()) / "agent_integration_report.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 720, "Deviation: pressure reading 152 PSI exceeds the 150 PSI limit.")
    c.save()

    read_observation = loop.execute("read_document", {"path": str(pdf_path)})
    check("read_document via ReactLoop returns wrapped content", "BEGIN DOCUMENT CONTENT" in read_observation)
    check("read_document via ReactLoop returns the real extracted text", "152 PSI" in read_observation)

    search_observation = loop.execute("search_knowledge", {"query": "pressure limit"})
    check("search_knowledge via ReactLoop runs without crashing",
          isinstance(search_observation, str) and len(search_observation) > 0)
    check("search_knowledge honestly reports unavailable (chromadb absent in this sandbox)",
          "unavailable" in search_observation)


def test_react_loop_unknown_action_unaffected():
    loop = ReactLoop(Settings())
    check("Unknown actions still fall through correctly",
          loop.execute("not_a_real_action", {}) == "Unknown action: not_a_real_action")


# ─── Verifier compatibility — agent/verifier.py itself is untouched;
#     confirming it handles the new tools' output correctly with zero
#     changes, as claimed in the audit's Section F. ──────────────────────

def test_verifier_accepts_successful_calculate():
    v = Verifier(Settings())
    result = v.verify("calculate", {"expression": "2+2"}, "2 + 2 = 4", 0.01)
    check("Verifier accepts a clean calculate() success", result.success is True)


def test_verifier_flags_calculate_error_as_failure():
    v = Verifier(Settings())
    result = v.verify("calculate", {"expression": "bad"}, "Error executing calculate: Empty expression", 0.01)
    check("Verifier flags a calculate() error exactly like any other tool's error", result.success is False)


def test_verifier_known_limitation_document_content_can_false_positive():
    """Documented, not fixed: Verifier does a substring scan across the
    WHOLE observation, including embedded document text. This is a
    pre-existing Verifier characteristic (already true for browser/
    vision when page/screen content happens to contain one of the
    failure phrases) that document tools also inherit — not something
    Milestone 3 introduced. Recorded here as a known, verified
    limitation rather than silently patched, since fixing it means
    editing agent/verifier.py — out of this milestone's scope per Rule 1
    unless explicitly authorized."""
    v = Verifier(Settings())
    doc_observation = wrap_untrusted(
        "Inspection notes: the technician could not find the calibration "
        "tag on unit 4, otherwise no deviations.",
        source_label="inspection_report.pdf",
    )
    result = v.verify("read_document", {"path": "inspection_report.pdf"}, doc_observation, 0.2)
    check("KNOWN LIMITATION (pre-existing, documented, not fixed here): legitimate "
          "document text containing a failure-signal phrase reads as a failure",
          result.success is False)


def main():
    test_system_prompt_mentions_all_four_tools()
    test_system_prompt_has_document_trust_instruction()
    test_react_loop_dispatches_calculate()
    test_react_loop_calculate_error_wrapped_consistently()
    test_react_loop_dispatches_create_document()
    test_react_loop_dispatches_read_document_and_search_knowledge()
    test_react_loop_unknown_action_unaffected()
    test_verifier_accepts_successful_calculate()
    test_verifier_flags_calculate_error_as_failure()
    test_verifier_known_limitation_document_content_can_false_positive()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Sovereign Workbench agent integration (Milestone 3) verified.")


if __name__ == "__main__":
    main()
