"""
Milestone 6 — live End-to-End Sovereign SAM test.

Nothing is mocked here: real Brain, real Planner, real ReAct, real
tools, real Verifier, real SocketGuard. This requires a reachable
Ollama with the configured models pulled. It is NOT run as part of
this project's offline verification (no Ollama in that sandbox) — it
exists to be run for real on your actual dev machine.

Per the repository's own established _offline/_live convention
(test_founder_mode_offline.py vs test_founder_mode_live.py): if the
live dependency isn't reachable, every test function prints exactly

    Insufficient data — not verified in this environment.

and returns cleanly rather than failing — an unreachable Ollama is an
environment fact, not a product defect, and is never reported as one.

IMPORTANT: the Ollama-reachability check is done at the top of EVERY
individual test function, not only in main(). A file with module-level
functions named test_* is exactly what pytest auto-discovers and calls
directly — which bypasses the `if __name__ == "__main__":` block
entirely. Gating only inside main() protected the
`python3 test_sovereign_e2e_live.py` invocation but not a pytest-driven
one, which reached Brain.process() -> _ensure_model() and raised
"RuntimeError: Ollama is not running. Start it with: ollama serve"
uncaught. Fixed by checking reachability first inside each function.

Usage:
    HOME=/tmp/sam_smoke_e2e_live python3 tests/test_sovereign_e2e_live.py
    (or) pytest tests/test_sovereign_e2e_live.py
"""

import socket
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.react_loop import ReactLoop  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.session import Session  # noqa: E402
from main import run_task_with_optional_sovereign_mode  # noqa: E402
from sovereign.security.network_guard import NetworkPolicyViolation  # noqa: E402

results = []
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "sovereign"
INSPECTION_REPORT = FIXTURES_DIR / "inspection_report.pdf"
PLANT_SOP = FIXTURES_DIR / "plant_sop.docx"

INSUFFICIENT_DATA_MESSAGE = "Insufficient data — not verified in this environment."

OFFICIAL_DEMO_TASK = (
    f"Review the local file {INSPECTION_REPORT} against the applicable SOP "
    f"at {PLANT_SOP}, identify the deviations, then calculate the required "
    "value, and finally prepare an approval note with the supporting evidence."
)
ADAPTIVE_EQUIVALENT_TASK = (
    f"Review the local file {INSPECTION_REPORT} against the applicable SOP "
    f"at {PLANT_SOP}, identify deviations, calculate the required value, "
    "and prepare an approval note with supporting evidence."
)


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _ollama_reachable(settings, timeout=2) -> bool:
    try:
        import requests
        r = requests.get(f"{settings.ollama_host}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _chromadb_installed() -> bool:
    try:
        import chromadb  # noqa: F401
        return True
    except ImportError:
        return False


def _require_ollama(settings) -> bool:
    """Returns True if Ollama is reachable. Otherwise prints the exact
    required message and returns False. Call this FIRST, before
    constructing/calling Brain or Planner, in every test function —
    not just in main() — so a real live-dependency call is never
    reached regardless of how the function gets invoked."""
    if _ollama_reachable(settings):
        return True
    print(INSUFFICIENT_DATA_MESSAGE)
    print(f"(Ollama not reachable at {settings.ollama_host}.)")
    return False


def test_live_planned_path_real_model():
    settings = Settings()
    if not _require_ollama(settings):
        return
    settings.sovereign_mode = True
    settings.sovereign_output_dir = str(Path(tempfile.mkdtemp()) / "output")
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")

    loop = ReactLoop(settings)
    session = Session(user_input=OFFICIAL_DEMO_TASK, identity={}, memories=[], founder_context="", settings=settings)
    from core.brain import Brain
    brain = Brain(settings)

    # main.py's real flow calls brain.process(session) once up front to get
    # the initial classification, then passes that as initial_response.
    initial_response = brain.process(session)
    check("Live Brain returned a real classification for the demo task", initial_response is not None)

    original_connect = socket.socket.connect
    result_text, network_report = run_task_with_optional_sovereign_mode(
        loop, settings, OFFICIAL_DEMO_TASK, brain, session, "", initial_response, threading.Event(),
    )

    check("Live run produced a non-empty result", bool(result_text and result_text.strip()))
    check("Sovereign Mode produced a real network report", network_report is not None)
    check("Guard restored socket.socket.connect after the live run", socket.socket.connect is original_connect)

    out_dir = Path(settings.sovereign_output_dir)
    docx_files = list(out_dir.glob("*.docx"))
    check("A DOCX was actually generated by the real agent workflow", len(docx_files) >= 1)
    if docx_files:
        import docx as docx_lib
        doc = docx_lib.Document(str(docx_files[0]))
        full_text = "\n".join(p.text for p in doc.paragraphs)
        check("The generated DOCX references the measured pressure value",
              "165" in full_text)
        check("The generated DOCX references the SOP pressure limit",
              "150" in full_text)
    else:
        print("NOTE: model did not create a DOCX for this run — this reflects real model "
              "behavior for this prompt/model, not a framework bug. Insufficient data on "
              "whether this is consistent — rerun and/or inspect the transcript.")


def test_live_network_attack_is_blocked_during_real_run():
    # No Brain/Planner dependency — this one doesn't actually need
    # Ollama, so it isn't gated behind _require_ollama(). It's here
    # because it belongs thematically with the live sovereignty demo,
    # not because it needs a live model.
    settings = Settings()
    settings.sovereign_mode = True
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")
    from sovereign.security import SocketGuard

    original_connect = socket.socket.connect
    with SocketGuard(settings, task_label="live-attack-test") as guard:
        try:
            socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("8.8.8.8", 80))
            blocked = False
        except NetworkPolicyViolation:
            blocked = True
        except OSError:
            blocked = False
    check("Deliberate external connection is blocked before it reaches the OS layer", blocked is True)
    check("The block was recorded in the real report", guard.report().blocked_count >= 1)
    check("socket.socket.connect is restored to the original", socket.socket.connect is original_connect)


def test_live_adaptive_path_real_model():
    settings = Settings()
    if not _require_ollama(settings):
        return
    loop = ReactLoop(settings)
    check("Adaptive wording still avoids the Planner trigger", loop._looks_multi_step(ADAPTIVE_EQUIVALENT_TASK) is False)

    session = Session(user_input=ADAPTIVE_EQUIVALENT_TASK, identity={}, memories=[], founder_context="", settings=settings)
    from core.brain import Brain
    brain = Brain(settings)
    initial_response = brain.process(session)

    result = loop.run_planned_task(
        task=ADAPTIVE_EQUIVALENT_TASK, brain=brain, session=session, founder_context="",
        initial_response=initial_response, cancel_event=threading.Event(),
    )
    check("The live adaptive path produced a real result", bool(result and result.strip()))


def main():
    settings = Settings()

    if not FIXTURES_DIR.exists() or not INSPECTION_REPORT.exists():
        print(INSUFFICIENT_DATA_MESSAGE)
        print("(Fixtures missing — run tests/fixtures/sovereign/generate_fixtures.py first.)")
        sys.exit(0)

    if not _ollama_reachable(settings):
        print(INSUFFICIENT_DATA_MESSAGE)
        print(f"(Ollama not reachable at {settings.ollama_host}.)")
        sys.exit(0)

    print(f"Ollama is reachable at {settings.ollama_host}. Real ChromaDB installed: {_chromadb_installed()}.")
    if not _chromadb_installed():
        print("NOTE: chromadb is not installed here — search_knowledge will honestly report "
              "'unavailable' during this run rather than fabricate results. That's expected, "
              "not a failure of this test.")

    test_live_planned_path_real_model()
    test_live_network_attack_is_blocked_during_real_run()
    test_live_adaptive_path_real_model()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Sovereign Workbench E2E workflow (Milestone 6, live) verified.")


if __name__ == "__main__":
    main()
