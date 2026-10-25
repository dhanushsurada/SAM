"""Focused offline regressions for C1-C3 recovery.

Run with the repository environment: python3 tests/test_c1_c3_offline.py
Ollama HTTP is mocked at the requests boundary; the actual NDJSON parser,
manager state decisions, and CLI JSON encoder are exercised.
"""

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.model_manager import ModelManager, ModelPullError
from runtime.health.status import RuntimeStatus
from runtime.ollama.manager import OllamaManager
import sam_cli


class RuntimeStatusTests(unittest.TestCase):
    def test_not_installed_is_serializable(self):
        self.assertEqual(RuntimeStatus.NOT_INSTALLED.value, "NOT_INSTALLED")
        self.assertEqual(json.dumps({"state": RuntimeStatus.NOT_INSTALLED.value}),
                         '{"state": "NOT_INSTALLED"}')


class OllamaManagerTests(unittest.TestCase):
    @patch("runtime.ollama.manager.requests.get", side_effect=OSError("offline"))
    @patch("runtime.ollama.manager.find_ollama_executable", return_value=None)
    def test_local_missing_binary_reports_not_installed(self, find_exe, get):
        result = OllamaManager().status()
        self.assertEqual(result["state"], RuntimeStatus.NOT_INSTALLED.value)
        self.assertEqual(result["models"], [])

    @patch("runtime.ollama.manager.requests.get", side_effect=OSError("offline"))
    @patch("runtime.ollama.manager.find_ollama_executable", return_value="/usr/bin/ollama")
    def test_installed_but_offline_reports_stopped(self, find_exe, get):
        self.assertEqual(OllamaManager().status()["state"], RuntimeStatus.STOPPED.value)

    def test_remote_endpoint_is_never_started_by_sam(self):
        manager = OllamaManager("https://ollama.example:11434")
        with patch.object(manager, "status", return_value={"state": "STOPPED"}), \
             patch("runtime.ollama.manager.subprocess.Popen") as popen:
            result = manager.start()
        self.assertFalse(result["ok"])
        popen.assert_not_called()

    def test_ready_status_reports_model_names(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"models": [{"name": "qwen:latest"}]}
        with patch("runtime.ollama.manager.requests.get", return_value=response):
            result = OllamaManager().status()
        self.assertEqual(result["state"], RuntimeStatus.READY.value)
        self.assertEqual(result["models"], ["qwen:latest"])


class ModelPullTests(unittest.TestCase):
    def setUp(self):
        self.manager = ModelManager.__new__(ModelManager)
        self.manager.settings = SimpleNamespace(ollama_host="http://127.0.0.1:11434")

    def test_pull_parses_ndjson_and_closes_response(self):
        response = MagicMock(status_code=200)
        response.iter_lines.return_value = [
            b'{"status":"pulling manifest"}',
            b'{"status":"success"}',
            b'{"status":"must not be read"}',
        ]
        with patch("core.model_manager.requests.post", return_value=response) as post:
            events = list(self.manager.pull("qwen3:4b"))
        self.assertEqual([event["status"] for event in events],
                         ["pulling manifest", "success"])
        self.assertEqual(post.call_args.kwargs["json"], {"model": "qwen3:4b"})
        self.assertTrue(post.call_args.kwargs["stream"])
        response.close.assert_called_once()

    def test_pull_surfaces_server_error_and_closes_response(self):
        response = MagicMock(status_code=200)
        response.iter_lines.return_value = [b'{"error":"disk full"}']
        with patch("core.model_manager.requests.post", return_value=response):
            with self.assertRaisesRegex(ModelPullError, "disk full"):
                list(self.manager.pull("qwen3:4b"))
        response.close.assert_called_once()

    def test_pull_rejects_invalid_stream_and_model_name(self):
        response = MagicMock(status_code=200)
        response.iter_lines.return_value = [b"not-json"]
        with patch("core.model_manager.requests.post", return_value=response):
            with self.assertRaises(ModelPullError):
                list(self.manager.pull("qwen3"))
        with self.assertRaises(ModelPullError):
            list(self.manager.pull(" "))


class CliJsonTests(unittest.TestCase):
    def test_json_encoder_emits_one_parseable_line(self):
        from io import StringIO
        output = StringIO()
        with patch("sys.stdout", output):
            code = sam_cli._emit_json({"success": True, "count": 2})
        lines = output.getvalue().splitlines()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0]), {"success": True, "count": 2})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
