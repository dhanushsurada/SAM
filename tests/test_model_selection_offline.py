"""
Offline test suite for M6.2 — actual local model selection/configuration.

Covers Brain.list_installed_models() (read-only discovery), the extended
first-run Step 2 in main.py's _run_first_run_setup(), the runtime
"model X" command, and the Settings.model_explicitly_set guard in
config/settings.py's _select_model() that stops RAM-based auto-detection
from silently overwriting an explicit choice.

Mocks core.brain.requests.get so nothing here needs a real Ollama
install. Tests that touch Settings persistence patch
config.settings.SAM_DATA_DIR to an isolated tempdir, mirroring how
test_identity_setup_offline.py patches memory.identity.IDENTITY_PATH —
SAM_DATA_DIR is computed once at import time from $HOME, so this is the
reliable way to control settings.yaml location per test within one
process (an env var change after import wouldn't take effect).

Usage:
    HOME=/tmp/sam_smoke_model_selection python3 tests/test_model_selection_offline.py
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
import config.settings as settings_module  # noqa: E402
from config.settings import Settings  # noqa: E402
from core.brain import Brain, BrainResponse  # noqa: E402
from core.session import Session  # noqa: E402
from agent.react_loop import ReactLoop  # noqa: E402
from agent import planner  # noqa: E402
import memory.identity as identity_module  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def _fresh_identity_path() -> Path:
    return Path(tempfile.mkdtemp()) / "identity.json"


def _fresh_sam_data_dir() -> Path:
    return Path(tempfile.mkdtemp())


def _mock_tags_response(model_names):
    """Mock requests.Response-like object for Ollama's GET /api/tags."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"models": [{"name": n} for n in model_names]}
    return resp


# ─── 1-4: Brain.list_installed_models() — read-only discovery ────────────

def test_list_installed_models_returns_real_names():
    brain = Brain(Settings())
    with patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:14b", "qwen2.5:7b"])):
        models = brain.list_installed_models()
    check("list_installed_models returns the names Ollama reports", models == ["qwen2.5:14b", "qwen2.5:7b"])


def test_list_installed_models_empty_when_nothing_installed():
    brain = Brain(Settings())
    with patch("core.brain.requests.get", return_value=_mock_tags_response([])):
        models = brain.list_installed_models()
    check("list_installed_models returns an empty list (not an error) when nothing is installed", models == [])


def test_list_installed_models_raises_when_ollama_unreachable():
    brain = Brain(Settings())
    with patch("core.brain.requests.get", side_effect=ConnectionError("no network")):
        try:
            brain.list_installed_models()
            check("list_installed_models raises RuntimeError when Ollama is unreachable", False)
        except RuntimeError:
            check("list_installed_models raises RuntimeError when Ollama is unreachable", True)


def test_list_installed_models_is_read_only():
    brain_src = Path(__file__).parent.parent.joinpath("core", "brain.py").read_text()
    method_src = brain_src.split("def list_installed_models")[1].split("def _ensure_model")[0]
    check(
        "Brain.list_installed_models() contains no /api/pull or subprocess call (read-only, per M6.2 scope)",
        "/api/pull" not in method_src and "subprocess" not in method_src,
    )


# ─── 5-7: explicit choice beats RAM auto-detection (_select_model unit) ──

def test_fresh_settings_defaults_to_not_explicit():
    s = Settings()
    check("A fresh Settings() has model_explicitly_set = False", s.model_explicitly_set is False)
    check("A fresh Settings() keeps the hardcoded primary_model default", s.primary_model == "qwen2.5:14b")
    check("A fresh Settings() keeps the hardcoded fallback_model default", s.fallback_model == "qwen2.5:7b")


def test_ram_auto_select_still_works_without_explicit_choice():
    s = Settings.__new__(Settings)
    s.primary_model, s.fallback_model, s.model_explicitly_set = "qwen2.5:14b", "qwen2.5:7b", False
    s.detected_ram_gb = 32
    s._select_model()
    check("RAM-based auto-select still upgrades primary_model when no explicit choice exists", s.primary_model == "qwen2.5:32b")


def test_explicit_choice_survives_ram_auto_detection():
    s = Settings.__new__(Settings)
    s.primary_model, s.fallback_model, s.model_explicitly_set = "qwen2.5:32b", "qwen2.5:7b", True
    s.detected_ram_gb = 16  # would normally downgrade to 14b
    s._select_model()
    check("An explicit choice is not overwritten by RAM-based auto-detection", s.primary_model == "qwen2.5:32b")


def test_explicit_choice_survives_when_ram_is_never_detected():
    s = Settings.__new__(Settings)
    s.primary_model, s.fallback_model, s.model_explicitly_set = "qwen2.5:32b", "qwen2.5:7b", True
    s.detected_ram_gb = None  # e.g. Linux, where _detect_hardware() never sets this
    s._select_model()
    check("An explicit choice survives on platforms where RAM is never detected (e.g. Linux)", s.primary_model == "qwen2.5:32b")


# ─── 8-11: real end-to-end restart, through __post_init__ ────────────────

def test_fresh_install_auto_selects_via_real_hardware_detection():
    data_dir = _fresh_sam_data_dir()
    with patch.object(settings_module, "SAM_DATA_DIR", data_dir):
        with patch.object(Settings, "_detect_hardware", lambda self: setattr(self, "detected_ram_gb", 32)):
            s = Settings()
    check("A fresh install with no explicit choice still auto-selects by RAM tier", s.primary_model == "qwen2.5:32b")
    check("Auto-selection alone does not mark the choice as explicit", s.model_explicitly_set is False)


def test_explicit_choice_persists_across_simulated_restart():
    data_dir = _fresh_sam_data_dir()
    with patch.object(settings_module, "SAM_DATA_DIR", data_dir):
        s1 = Settings()
        s1.primary_model, s1.fallback_model, s1.model_explicitly_set = "qwen2.5:32b", "qwen2.5:14b", True
        s1.save()
        s2 = Settings()  # brand-new instance, simulating a restart
    check("primary_model survives a simulated restart", s2.primary_model == "qwen2.5:32b")
    check("fallback_model survives a simulated restart", s2.fallback_model == "qwen2.5:14b")
    check("model_explicitly_set survives a simulated restart", s2.model_explicitly_set is True)


def test_explicit_choice_survives_restart_even_when_hardware_detection_succeeds():
    """The exact scenario the M6.2 audit found broken: persist an explicit
    choice, then restart on a machine where _detect_hardware() succeeds
    (as it would on real Mac/Windows) and would, without the fix, have
    silently downgraded primary_model on every boot."""
    data_dir = _fresh_sam_data_dir()
    with patch.object(settings_module, "SAM_DATA_DIR", data_dir):
        s1 = Settings()
        s1.primary_model, s1.model_explicitly_set = "qwen2.5:32b", True
        s1.save()

        with patch.object(Settings, "_detect_hardware", lambda self: setattr(self, "detected_ram_gb", 16)):
            s2 = Settings()  # full real __post_init__, simulated Mac/Windows detection
    check(
        "An explicit choice survives a full restart even when hardware detection succeeds "
        "and would otherwise suggest a different tier",
        s2.primary_model == "qwen2.5:32b",
    )
    check("detected_ram_gb reflects the simulated detection (sanity check the mock fired)", s2.detected_ram_gb == 16)


def test_runtime_model_command_change_persists_across_restart():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:32b", "qwen2.5:14b"])):
        sam = main.SAM(start_in_text_mode=True)
        sam._handle_command("model qwen2.5:32b")
        s2 = Settings()  # simulated restart
    check("A runtime model change is still there after a simulated restart", s2.primary_model == "qwen2.5:32b")
    check("The persisted choice is marked explicit", s2.model_explicitly_set is True)


# ─── 12-17: first-run Step 2 ───────────────────────────────────────────────

def test_first_run_step2_offers_real_choice_when_models_installed():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:32b", "qwen2.5:14b"])):
        with patch("builtins.input", side_effect=["NOVA", "qwen2.5:32b", "skip"]):
            sam = main.SAM(start_in_text_mode=True)
            sam._run_first_run_setup()
    check("Name is set from Step 1's input", sam._display_name == "NOVA")
    check("Primary model is set from the real installed list in Step 2", sam.settings.primary_model == "qwen2.5:32b")
    check("The choice is marked explicit", sam.settings.model_explicitly_set is True)
    check("Choosing 'skip' for fallback leaves fallback_model unchanged", sam.settings.fallback_model == "qwen2.5:7b")


def test_first_run_step2_accepts_defaults_on_blank_input():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:14b", "qwen2.5:7b"])):
        with patch("builtins.input", side_effect=["", "", ""]):
            sam = main.SAM(start_in_text_mode=True)
            sam._run_first_run_setup()
    check("Blank input for name accepts the default (VEDA)", sam._display_name == "VEDA")
    check("Blank input for primary model accepts the shown default", sam.settings.primary_model == "qwen2.5:14b")
    check("Accepting the shown default via Step 2 still marks the choice explicit", sam.settings.model_explicitly_set is True)
    check("Blank input for fallback accepts the shown default fallback", sam.settings.fallback_model == "qwen2.5:7b")


def test_first_run_step2_rejects_unlisted_model_keeps_default():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:14b"])):
        with patch("builtins.input", side_effect=["NOVA", "totally-made-up-model"]):
            sam = main.SAM(start_in_text_mode=True)
            sam._run_first_run_setup()
    check("An unlisted primary model name is rejected; the shown default is used instead",
          sam.settings.primary_model == "qwen2.5:14b")


def test_first_run_step2_falls_back_when_ollama_unreachable():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", side_effect=ConnectionError("no network")):
        with patch("builtins.input", return_value="NOVA"):
            sam = main.SAM(start_in_text_mode=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                sam._run_first_run_setup()
            output = buf.getvalue()
    check("Setup still completes when Ollama is unreachable (unchanged M6.1 fail-soft behavior)", sam._display_name == "NOVA")
    check("No explicit model choice is recorded when there was nothing to choose from", sam.settings.model_explicitly_set is False)
    check("Step 2 output still shows a model check message", "Model check:" in output)


def test_first_run_step2_falls_back_when_ollama_reachable_but_empty():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response([])):
        with patch("builtins.input", return_value="NOVA"):
            sam = main.SAM(start_in_text_mode=True)
            sam._run_first_run_setup()
    check("Setup completes when Ollama is reachable but has nothing installed", sam._display_name == "NOVA")
    check("No explicit model choice is recorded when nothing was installed to choose from", sam.settings.model_explicitly_set is False)


def test_first_run_step_ordering_name_before_model():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:14b"])):
        with patch("builtins.input", side_effect=["NOVA", "qwen2.5:14b"]):
            sam = main.SAM(start_in_text_mode=True)
            buf = io.StringIO()
            with redirect_stdout(buf):
                sam._run_first_run_setup()
            output = buf.getvalue()
    check("STEP 1 (name) still appears before STEP 2 (model) in output, with real model selection active",
          output.index("STEP 1") < output.index("STEP 2"))


# ─── 18-20: runtime "model X" command ─────────────────────────────────────

def test_runtime_model_command_changes_and_marks_explicit():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:32b", "qwen2.5:14b"])):
        sam = main.SAM(start_in_text_mode=True)
        handled = sam._handle_command("model qwen2.5:32b")
    check("'model qwen2.5:32b' command is handled", handled is True)
    check("Runtime primary model updates immediately", sam.settings.primary_model == "qwen2.5:32b")
    check("Runtime model change is marked explicit", sam.settings.model_explicitly_set is True)


def test_runtime_model_command_rejects_uninstalled_name():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", return_value=_mock_tags_response(["qwen2.5:14b"])):
        sam = main.SAM(start_in_text_mode=True)
        original = sam.settings.primary_model
        handled = sam._handle_command("model totally-made-up-model")
    check("An uninstalled model name is still 'handled' (rejected with a message, not passed to the LLM)", handled is True)
    check("primary_model is unchanged after rejection", sam.settings.primary_model == original)
    check("model_explicitly_set is not set after a rejected change", sam.settings.model_explicitly_set is False)


def test_runtime_model_command_proceeds_unverified_when_ollama_unreachable():
    identity_path = _fresh_identity_path()
    data_dir = _fresh_sam_data_dir()
    with patch.object(identity_module, "IDENTITY_PATH", identity_path), \
         patch.object(settings_module, "SAM_DATA_DIR", data_dir), \
         patch("core.brain.requests.get", side_effect=ConnectionError("no network")):
        sam = main.SAM(start_in_text_mode=True)
        handled = sam._handle_command("model qwen2.5:32b")
    check("A model change is still accepted (unverified) when Ollama is unreachable — 'where practical' only", handled is True)
    check("primary_model updates even though it couldn't be verified", sam.settings.primary_model == "qwen2.5:32b")
    check("The unverified choice is still marked explicit", sam.settings.model_explicitly_set is True)


# ─── 21: existing per-feature model overrides need zero changes ──────────

def test_planner_automatically_picks_up_explicit_model_choice():
    """Confirms agent/planner.py needs no M6.2 changes — it already reads
    settings.primary_model dynamically (getattr(..., 'planner_model', None)
    or settings.primary_model), so an explicit choice just flows through."""
    settings = Settings()
    settings.primary_model = "qwen2.5:32b-explicit-choice"
    settings.model_explicitly_set = True
    with patch("agent.planner.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"response": '{"steps": [{"step": 1, "description": "x"}]}'}
        mock_post.return_value = mock_resp
        planner.decompose("do something", settings)
    sent_model = mock_post.call_args.kwargs["json"]["model"]
    check("planner.decompose sends the explicitly-chosen model to Ollama, unmodified", sent_model == "qwen2.5:32b-explicit-choice")


# ─── 22: Sovereign Mode unaffected ────────────────────────────────────────

def test_sovereign_mode_unaffected_by_model_selection():
    settings = Settings()
    settings.primary_model = "qwen2.5:32b"
    settings.model_explicitly_set = True
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
    check("Sovereign Mode still runs correctly with an explicit model selection set", report is not None)
    check("Task still completes correctly", bool(result_text))


def main_test_runner():
    test_list_installed_models_returns_real_names()
    test_list_installed_models_empty_when_nothing_installed()
    test_list_installed_models_raises_when_ollama_unreachable()
    test_list_installed_models_is_read_only()
    test_fresh_settings_defaults_to_not_explicit()
    test_ram_auto_select_still_works_without_explicit_choice()
    test_explicit_choice_survives_ram_auto_detection()
    test_explicit_choice_survives_when_ram_is_never_detected()
    test_fresh_install_auto_selects_via_real_hardware_detection()
    test_explicit_choice_persists_across_simulated_restart()
    test_explicit_choice_survives_restart_even_when_hardware_detection_succeeds()
    test_runtime_model_command_change_persists_across_restart()
    test_first_run_step2_offers_real_choice_when_models_installed()
    test_first_run_step2_accepts_defaults_on_blank_input()
    test_first_run_step2_rejects_unlisted_model_keeps_default()
    test_first_run_step2_falls_back_when_ollama_unreachable()
    test_first_run_step2_falls_back_when_ollama_reachable_but_empty()
    test_first_run_step_ordering_name_before_model()
    test_runtime_model_command_changes_and_marks_explicit()
    test_runtime_model_command_rejects_uninstalled_name()
    test_runtime_model_command_proceeds_unverified_when_ollama_unreachable()
    test_planner_automatically_picks_up_explicit_model_choice()
    test_sovereign_mode_unaffected_by_model_selection()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Model selection (M6.2) verified.")


if __name__ == "__main__":
    main_test_runner()
