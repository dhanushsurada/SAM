"""
Offline test suite for the M6.2 first-run assistant identity + model
setup — memory/identity.py's assistant_name as the single persistent
source of truth, main.py's first-run flow, and core/brain.py's
personalization. Covers the 20 scenarios from the M6.2 authorization.

Each test that needs a specific identity.json state patches
memory.identity.IDENTITY_PATH directly to an isolated tempfile path —
SAM_DATA_DIR/IDENTITY_PATH are computed once at import time from
$HOME, so this is the reliable way to control file state per test
within one process (an env var change after import wouldn't take
effect).

Usage:
    HOME=/tmp/sam_smoke_identity_setup python3 tests/test_identity_setup_offline.py
"""

import io
import sys
import tempfile
import threading
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import main  # noqa: E402
from agent.react_loop import ReactLoop  # noqa: E402
from config.settings import Settings, validate_assistant_name  # noqa: E402
from core.brain import Brain, BrainResponse  # noqa: E402
from core.session import Session  # noqa: E402
import memory.identity as identity_module  # noqa: E402
from memory.identity import DEFAULT_IDENTITY, Identity  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _fresh_identity_path() -> Path:
    return Path(tempfile.mkdtemp()) / "identity.json"


def _write_identity(path: Path, data: dict):
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


# ─── 1-3: first-run detection ─────────────────────────────────────────────

def test_fresh_identity_defaults_to_veda():
    path = _fresh_identity_path()
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
        check("Fresh install: is_first_run is True", sam._is_first_run is True)
        check("Fresh install: display name defaults to VEDA", sam._display_name == "VEDA")
        check("Fresh install: DEFAULT_IDENTITY's own default is VEDA", DEFAULT_IDENTITY["assistant_name"] == "VEDA")


def test_existing_identity_with_sam_remains_sam():
    path = _fresh_identity_path()
    _write_identity(path, {"name": "Dhanush", "assistant_name": "SAM", "about": "", "projects": [], "preferences": {}, "context": ""})
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
        check("Pre-existing SAM install: NOT treated as first-run", sam._is_first_run is False)
        check("Pre-existing SAM install: name stays SAM, not migrated to VEDA", sam._display_name == "SAM")


def test_existing_identity_with_custom_name_remains_unchanged():
    path = _fresh_identity_path()
    _write_identity(path, {"name": "Dhanush", "assistant_name": "NOVA", "setup_completed": True, "about": "", "projects": [], "preferences": {}, "context": ""})
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
        check("Completed setup with custom name: not re-prompted", sam._is_first_run is False)
        check("Completed setup with custom name: preserved exactly", sam._display_name == "NOVA")


def test_interrupted_first_run_resumes():
    path = _fresh_identity_path()
    _write_identity(path, {"name": "Dhanush", "assistant_name": "VEDA", "setup_completed": False, "about": "", "projects": [], "preferences": {}, "context": ""})
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
        check("Explicit setup_completed=False (interrupted run) resumes setup", sam._is_first_run is True)


# ─── 4-8: name choices + validation ───────────────────────────────────────

def test_user_chooses_veda_sam_nova():
    for name in ["VEDA", "SAM", "NOVA"]:
        check(f"validate_assistant_name accepts '{name}'", validate_assistant_name(name) == name)


def test_multiword_name_works():
    check("Multi-word name 'My Assistant' is accepted", validate_assistant_name("My Assistant") == "My Assistant")


def test_invalid_names_rejected():
    for bad in ["", "   ", "a" * 100, "bad\x00name", "bad\nname"]:
        try:
            validate_assistant_name(bad)
            check(f"Invalid name rejected: {bad!r}", False)
        except ValueError:
            check(f"Invalid name rejected: {bad!r}", True)


# ─── 9-10: persistence + reload ───────────────────────────────────────────

def test_persists_through_identity_update_and_reload():
    path = _fresh_identity_path()
    with patch.object(identity_module, "IDENTITY_PATH", path):
        Identity().update({"assistant_name": "JARVIS", "setup_completed": True})
        reloaded = Identity().load()
        check("assistant_name persists through Identity.update()", reloaded["assistant_name"] == "JARVIS")

        sam2 = main.SAM(start_in_text_mode=True)
        check("A fresh SAM() instance picks up the persisted name on 'restart'", sam2._display_name == "JARVIS")
        check("A fresh SAM() instance sees setup as already complete", sam2._is_first_run is False)


# ─── 11-13: first-run flow behavior ────────────────────────────────────────

def test_first_run_flow_names_then_checks_model_in_order():
    path = _fresh_identity_path()
    with patch.object(identity_module, "IDENTITY_PATH", path):
        with patch("builtins.input", return_value="NOVA"):
            sam = main.SAM(start_in_text_mode=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                sam._run_first_run_setup()
            output = buf.getvalue()

    check("Setup completes and persists the chosen name", sam._display_name == "NOVA")
    persisted = None
    with patch.object(identity_module, "IDENTITY_PATH", path):
        persisted = Identity().load()
    check("Persisted assistant_name matches the chosen name", persisted.get("assistant_name") == "NOVA")
    check("Persisted setup_completed is True", persisted.get("setup_completed") is True)
    check("Name step (STEP 1) appears before model step (STEP 2) in the actual output",
          output.index("STEP 1") < output.index("STEP 2"))
    check("is_first_run is cleared in-memory after setup completes", sam._is_first_run is False)


def test_completed_setup_is_skipped_on_next_launch():
    path = _fresh_identity_path()
    _write_identity(path, {"name": "Dhanush", "assistant_name": "VEDA", "setup_completed": True, "about": "", "projects": [], "preferences": {}, "context": ""})
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
    check("Completed setup is not re-triggered", sam._is_first_run is False)


def test_cli_name_override_skips_interactive_prompt_but_still_persists():
    path = _fresh_identity_path()
    with patch.object(identity_module, "IDENTITY_PATH", path):
        with patch("builtins.input", side_effect=AssertionError("should not prompt when --name was given")):
            sam = main.SAM(start_in_text_mode=True)
            sam._display_name = validate_assistant_name("JARVIS")
            sam._name_overridden_via_cli = True
            sam._run_first_run_setup()
        persisted = Identity().load()
    check("--name on first run skips the interactive prompt (no input() call)", sam._display_name == "JARVIS")
    check("--name on first run still persists the chosen name", persisted.get("assistant_name") == "JARVIS")


# ─── 14-15: runtime display + runtime command ─────────────────────────────

def test_brain_personalizes_from_session_identity():
    settings = Settings()
    session = Session(user_input="hi", identity={"assistant_name": "NOVA"}, memories=[], founder_context="", settings=settings)
    brain = Brain(settings)
    messages = brain._build_messages(session)
    check("Brain's system message uses the identity's assistant_name", "You are NOVA" in messages[0]["content"])


def test_runtime_name_command_changes_and_persists():
    path = _fresh_identity_path()
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
        handled = sam._handle_command("name NOVA")
        check("'name NOVA' command is handled", handled is True)
        check("Runtime display updates immediately", sam._display_name == "NOVA")
        persisted = Identity().load()
    check("Runtime name change persists through Identity", persisted.get("assistant_name") == "NOVA")


def test_runtime_name_command_rejects_invalid_and_keeps_old_name():
    path = _fresh_identity_path()
    with patch.object(identity_module, "IDENTITY_PATH", path):
        sam = main.SAM(start_in_text_mode=True)
        original = sam._display_name
        sam._handle_command("name    ")  # whitespace-only after "name "
        check("Invalid runtime name change is rejected, old name kept", sam._display_name == original)


# ─── 16: functional literals unchanged ────────────────────────────────────

def test_functional_sam_literals_unchanged_in_source():
    main_src = Path(__file__).parent.parent.joinpath("main.py").read_text()
    for literal in ['"sam sleep"', '"sam stop"', 'goodbye sam', "Say 'Hey SAM'"]:
        check(f"Functional literal {literal!r} is still present, unchanged", literal in main_src)


# ─── 17: Sovereign Mode still works alongside a custom name ──────────────

def test_sovereign_mode_works_with_custom_display_name():
    settings = Settings()
    settings.sovereign_mode = True
    settings.sovereign_network_log = str(Path(tempfile.mkdtemp()) / "network_guard.jsonl")
    loop = ReactLoop(settings)
    session = Session(user_input="", identity={"assistant_name": "NOVA"}, memories=[], founder_context="", settings=settings)
    mock_brain = MagicMock()
    mock_brain.process.side_effect = [BrainResponse(text="done", action=None, action_payload=None, raw="")]
    initial_response = BrainResponse(text="", action="calculate", action_payload={"expression": "2+2"}, raw="")

    with patch("agent.planner.decompose", return_value=[{"step": 1, "description": "a"}, {"step": 2, "description": "b"}]):
        result_text, report = main.run_task_with_optional_sovereign_mode(
            loop, settings, "do one thing then finally another", mock_brain, session, "",
            initial_response, threading.Event(),
        )
    check("Sovereign Mode still runs correctly regardless of display name", report is not None)
    check("Task still completes correctly", bool(result_text))


# ─── 19: internal SAM identifiers unchanged ───────────────────────────────

def test_internal_sam_identifiers_unchanged():
    check("The class is still named SAM", main.SAM.__name__ == "SAM")
    check("The logger namespace is still 'SAM'", main.logger.name == "SAM")


# ─── 20: existing profile functionality intact ────────────────────────────

def test_sam_cli_profile_reference_untouched():
    sam_cli_src = Path(__file__).parent.parent.joinpath("sam_cli.py").read_text()
    check("sam_cli.py's profile printer still reads assistant_name from Identity, unmodified",
          "identity.get('assistant_name', 'SAM')" in sam_cli_src)


def main_test_runner():
    test_fresh_identity_defaults_to_veda()
    test_existing_identity_with_sam_remains_sam()
    test_existing_identity_with_custom_name_remains_unchanged()
    test_interrupted_first_run_resumes()
    test_user_chooses_veda_sam_nova()
    test_multiword_name_works()
    test_invalid_names_rejected()
    test_persists_through_identity_update_and_reload()
    test_first_run_flow_names_then_checks_model_in_order()
    test_completed_setup_is_skipped_on_next_launch()
    test_cli_name_override_skips_interactive_prompt_but_still_persists()
    test_brain_personalizes_from_session_identity()
    test_runtime_name_command_changes_and_persists()
    test_runtime_name_command_rejects_invalid_and_keeps_old_name()
    test_functional_sam_literals_unchanged_in_source()
    test_sovereign_mode_works_with_custom_display_name()
    test_internal_sam_identifiers_unchanged()
    test_sam_cli_profile_reference_untouched()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Identity + first-run setup (M6.2) verified.")


if __name__ == "__main__":
    main_test_runner()
