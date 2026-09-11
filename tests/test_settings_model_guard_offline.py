"""
OFFLINE regression test — config/settings.py primary_model guard fix.

Phase 4 correctness-review finding: _select_model() unconditionally
overwrote primary_model with a RAM-tier default whenever detected_ram_gb
was not None — which _detect_hardware() guarantees on macOS/Windows even
when detection itself fails (its except: clause falls back to 16). This
silently clobbered any primary_model a user had set in
~/.sam_data/settings.yaml, on every single restart. Only Linux was
accidentally exempt, because _detect_hardware() has no Linux branch at
all, so detected_ram_gb simply stays None there.

Fix: a model_explicitly_set guard field, set when the loaded YAML
carries an explicit primary_model of its own (see config/settings.py's
_load_yaml() for the exact precedence rule against a persisted
model_explicitly_set), checked first thing in _select_model().

This is deliberately narrow: it proves the two cases the Phase 4 fix was
scoped to (A: no override -> auto-select still works, B: explicit
override -> survives). It does NOT attempt to test Brain.list_installed_models(),
main.py's first-run flow, the runtime "model X" command, or Sovereign
Mode — tests/test_model_selection_offline.py already specs those as a
separate, larger, not-yet-implemented feature (M6.2 proper), which is out
of Phase 4 scope (installer/deployment, not SAM Core).

Each case runs Settings() in a fresh subprocess under an isolated HOME,
for the same reason established elsewhere in this suite: SAM_DATA_DIR is
computed once at config.settings import time from $HOME, so an in-process
HOME change after that first import would silently no-op.

Never touches the real ~/.sam_data.

Usage:
    python3 tests/test_settings_model_guard_offline.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
results = []


def check(label, condition):
    results.append(bool(condition))
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")


def _settings_snapshot(home: Path, yaml_text: str | None, fake_ram_gb: int) -> dict:
    """Writes yaml_text (if given) to ~/.sam_data/settings.yaml, then
    constructs a real Settings() in a fresh subprocess with
    _detect_hardware() patched to a fixed RAM value — patched rather than
    relying on this sandbox's real RAM so the test is deterministic and
    platform-independent (mirrors _detect_hardware()'s real macOS/Windows
    behavior: detected_ram_gb ends up a concrete int either way)."""
    sam_data = home / ".sam_data"
    sam_data.mkdir(parents=True, exist_ok=True)
    if yaml_text is not None:
        (sam_data / "settings.yaml").write_text(yaml_text)

    script = (
        f"import sys; sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from unittest.mock import patch\n"
        "import json\n"
        "from config.settings import Settings\n"
        "with patch.object(Settings, '_detect_hardware', "
        f"lambda self: setattr(self, 'detected_ram_gb', {fake_ram_gb})):\n"
        "    s = Settings()\n"
        "print(json.dumps({'primary_model': s.primary_model, "
        "'model_explicitly_set': s.model_explicitly_set}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env={"HOME": str(home), "PATH": "/usr/bin:/bin"},
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        raise AssertionError(f"subprocess failed:\n{result.stderr}")
    return json.loads(result.stdout.strip().splitlines()[-1])


# ─── A: no explicit primary_model -> RAM-tier/default selection works ────

def test_no_yaml_at_all_still_auto_selects_by_ram():
    with tempfile.TemporaryDirectory() as tmp:
        snap = _settings_snapshot(Path(tmp), None, fake_ram_gb=32)
        check("no settings.yaml at all -> still auto-selects by RAM tier (32GB -> 32b)",
              snap["primary_model"] == "qwen2.5:32b")
        check("no settings.yaml at all -> model_explicitly_set stays False",
              snap["model_explicitly_set"] is False)


def test_yaml_with_unrelated_keys_still_auto_selects_by_ram():
    with tempfile.TemporaryDirectory() as tmp:
        snap = _settings_snapshot(Path(tmp), "wake_word: 'hey nova'\n", fake_ram_gb=8)
        check("settings.yaml present but doesn't mention primary_model -> RAM tier still applies (8GB -> 7b)",
              snap["primary_model"] == "qwen2.5:7b")
        check("settings.yaml without primary_model -> model_explicitly_set stays False",
              snap["model_explicitly_set"] is False)


def test_ram_tier_changes_correctly_at_each_boundary():
    with tempfile.TemporaryDirectory() as tmp:
        snap = _settings_snapshot(Path(tmp), None, fake_ram_gb=16)
        check("16GB RAM tier -> 14b (unchanged boundary behavior)",
              snap["primary_model"] == "qwen2.5:14b")


# ─── B: explicit primary_model in configuration -> preserved ─────────────

def test_hand_written_yaml_with_primary_model_survives_ram_autodetect():
    with tempfile.TemporaryDirectory() as tmp:
        # A minimal, hand-written override — exactly what a user editing
        # ~/.sam_data/settings.yaml by hand would produce. No
        # model_explicitly_set key, because a human wouldn't know to add
        # that bookkeeping field themselves.
        snap = _settings_snapshot(Path(tmp), "primary_model: qwen2.5:7b\n", fake_ram_gb=64)
        check("hand-written primary_model survives even though 64GB RAM would normally pick 32b",
              snap["primary_model"] == "qwen2.5:7b")
        check("hand-written primary_model is recorded as explicit",
              snap["model_explicitly_set"] is True)


def test_saved_explicit_choice_survives_a_simulated_restart_with_ram_detection():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        # Simulates Settings.save() after a real explicit choice: dumps
        # every field, including model_explicitly_set: true.
        saved_yaml = (
            "primary_model: qwen2.5:32b\n"
            "fallback_model: qwen2.5:14b\n"
            "model_explicitly_set: true\n"
        )
        snap = _settings_snapshot(home, saved_yaml, fake_ram_gb=16)
        check("a .save()-style file with model_explicitly_set: true survives restart on a 16GB machine (would normally downgrade to 14b)",
              snap["primary_model"] == "qwen2.5:32b")
        check("model_explicitly_set stays True after restart",
              snap["model_explicitly_set"] is True)


def test_saved_auto_selection_is_reevaluated_not_frozen():
    """The companion case: a PREVIOUSLY auto-selected (not explicit) model,
    persisted by .save(), must still be free to re-evaluate on the next
    restart (e.g. after a RAM upgrade) rather than being treated as if it
    were explicit just because the key is present in the file."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        saved_yaml = (
            "primary_model: qwen2.5:14b\n"
            "model_explicitly_set: false\n"
        )
        snap = _settings_snapshot(home, saved_yaml, fake_ram_gb=32)
        check("a persisted AUTO-selected model (model_explicitly_set: false) re-evaluates on restart (16GB->14b file, now 32GB machine -> 32b)",
              snap["primary_model"] == "qwen2.5:32b")
        check("model_explicitly_set correctly stays False (was never an explicit choice)",
              snap["model_explicitly_set"] is False)


def main():
    print("=== Settings primary_model guard regression (Phase 4 fix) ===")
    print("\n--- A: no explicit choice -> RAM-tier/default selection ---")
    test_no_yaml_at_all_still_auto_selects_by_ram()
    test_yaml_with_unrelated_keys_still_auto_selects_by_ram()
    test_ram_tier_changes_correctly_at_each_boundary()
    print("\n--- B: explicit choice -> preserved ---")
    test_hand_written_yaml_with_primary_model_survives_ram_autodetect()
    test_saved_explicit_choice_survives_a_simulated_restart_with_ram_detection()
    test_saved_auto_selection_is_reevaluated_not_frozen()
    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Settings primary_model guard verified.")


if __name__ == "__main__":
    main()
