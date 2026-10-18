"""HTTP-level offline tests for POST /api/models/pull.

Requires the project's FastAPI/TestClient dependencies. Ollama itself is not
started; the TaskGateway's real streaming integration is exercised with a
small deterministic model-manager iterator.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
from interfaces.api import server


class PullGateway:
    def __init__(self, busy=False):
        self.busy = busy
        self.model_manager = self

    def get_brain_status(self):
        return {"busy": self.busy}

    def pull(self, name):
        yield {"status": "pulling manifest"}
        yield {"status": "success"}


class ModelPullRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app, client=("127.0.0.1", 12345))

    def test_streams_progress_and_terminal_success(self):
        with patch.object(server, "get_gateway", return_value=PullGateway()):
            response = self.client.post("/api/models/pull", json={"model": "qwen3:4b"})
        self.assertEqual(response.status_code, 200)
        self.assertIn('"status": "pulling manifest"', response.text.replace('": "', '":"').replace('":"', '": "'))
        self.assertIn('"status": "success"', response.text.replace('": "', '":"').replace('":"', '": "'))
        self.assertEqual(response.headers["content-type"].split(";")[0], "text/event-stream")

    def test_rejects_pull_while_gateway_is_busy(self):
        with patch.object(server, "get_gateway", return_value=PullGateway(busy=True)):
            response = self.client.post("/api/models/pull", json={"model": "qwen3:4b"})
        self.assertEqual(response.status_code, 409)

    def test_rejects_invalid_model_name_before_streaming(self):
        response = self.client.post("/api/models/pull", json={"model": ""})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__]))
    raise SystemExit(0 if result.wasSuccessful() else 1)
