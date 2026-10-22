import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runtime.compatibility import load_manifest
from runtime.config_migrations import (
    SCHEMA_KEY, SETTINGS_SCHEMA_VERSION, SettingsMigrationError, migrate_settings_file,
)
from runtime.environment_manager import EnvironmentCompatibilityManager


class EnvironmentManagerTests(unittest.TestCase):
    def test_setup_journal_is_atomic_and_preserves_completed_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            EnvironmentCompatibilityManager.record_setup_step("python", "complete", path=path)
            data = EnvironmentCompatibilityManager.record_setup_step("ollama", "started", path=path)
            self.assertEqual(data["steps"]["python"]["state"], "complete")
            self.assertEqual(json.loads(path.read_text())["steps"]["ollama"]["state"], "started")
            self.assertFalse(path.with_name("state.json.tmp").exists())

    def test_corrupt_setup_journal_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{not json")
            with self.assertRaisesRegex(RuntimeError, "preserve it and inspect"):
                EnvironmentCompatibilityManager.record_setup_step("python", "complete", path=path)
            self.assertEqual(path.read_text(), "{not json")

    def test_capability_probe_reports_installed_models_and_missing_choices(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): pass
            def read(self): return b'{"models":[{"name":"qwen:7b"}]}'

        manager = EnvironmentCompatibilityManager(
            manifest=load_manifest(), opener=lambda *_args, **_kwargs: Response())
        state = manager.capabilities({"primary_model": "qwen:7b", "vision_model": "moondream"})
        self.assertTrue(state["ollama"]["available"])
        self.assertTrue(state["ollama"]["configured_models"]["primary_model"]["available"])
        self.assertFalse(state["ollama"]["configured_models"]["vision_model"]["available"])

    def test_discovery_includes_platform_hardware_dependencies_and_tools(self):
        def runner(args, **_kwargs):
            return subprocess.CompletedProcess(args, 0, stdout="v20.1.0", stderr="")

        manager = EnvironmentCompatibilityManager(
            manifest=load_manifest(), which=lambda name: "/bin/" + name, runner=runner)
        with patch.object(manager, "_memory_gb", return_value=16):
            report = manager.discover()
        self.assertIn("architecture", report["os"])
        self.assertEqual(report["hardware"]["memory_gb"], 16)
        self.assertIn("core", report["dependencies"])
        self.assertTrue(report["tools"]["node"]["installed"])

    def test_dependency_resolution_keeps_core_and_optional_groups_separate(self):
        manager = EnvironmentCompatibilityManager(manifest=load_manifest())
        plan = manager.dependency_plan(["core"])
        self.assertEqual(plan["groups"], ["core"])
        self.assertIn("fastapi", " ".join(plan["requirements"]).lower())
        self.assertNotIn("faster-whisper", " ".join(plan["requirements"]).lower())
        self.assertIn("voice", load_manifest()["python"]["dependency_groups"])


class SettingsMigrationTests(unittest.TestCase):
    def test_old_settings_are_backed_up_and_user_values_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.yaml"
            original = b"primary_model: custom:13b\nfuture_option: keep-me\n"
            path.write_bytes(original)
            values = migrate_settings_file(path)
            self.assertEqual(path.with_name("settings.yaml.schema-0.bak").read_bytes(), original)
            self.assertEqual(values["primary_model"], "custom:13b")
            self.assertEqual(values["future_option"], "keep-me")
            self.assertEqual(values[SCHEMA_KEY], SETTINGS_SCHEMA_VERSION)
            self.assertEqual(migrate_settings_file(path), values)

    def test_future_settings_schema_is_never_downgraded(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.yaml"
            original = (SCHEMA_KEY + ": 99\nprimary_model: custom:13b\n").encode()
            path.write_bytes(original)
            with self.assertRaises(SettingsMigrationError):
                migrate_settings_file(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(path.with_name("settings.yaml.schema-99.bak").exists())


if __name__ == "__main__":
    unittest.main()
