"""
Offline test for the VEDA localhost API (M8-A, Step 1) —
GET /api/status, GET /api/model.

Brain._check_ollama and Brain._ensure_model are mocked exactly like
existing tests mock requests/Brain calls elsewhere in this suite — no
live Ollama needed, and no real model gets pulled or touched.

Usage:
    python3 tests/test_api_status_model_offline.py
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402
from config.settings import Settings  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


client = TestClient(app)
_expected = Settings()


# ─── GET /api/status ────────────────────────────────────────────────────

with patch("api.app._brain._check_ollama", return_value=True):
    r = client.get("/api/status")
    check("GET /api/status returns 200", r.status_code == 200)
    body = r.json()
    check("product field is VEDA-branded", body["product"].startswith("VEDA"))
    check("assistant_display_name is present", isinstance(body.get("assistant_display_name"), str))
    check("sovereign_mode is a bool", isinstance(body["sovereign_mode"], bool))
    check("ollama_reachable reflects the mocked True", body["ollama_reachable"] is True)
    check("uptime_seconds is non-negative", body["uptime_seconds"] >= 0)

with patch("api.app._brain._check_ollama", return_value=False):
    r = client.get("/api/status")
    check("ollama_reachable reflects the mocked False", r.json()["ollama_reachable"] is False)


# ─── GET /api/model — ready path ────────────────────────────────────────

with patch("api.app._brain._ensure_model", return_value="qwen2.5:14b"):
    r = client.get("/api/model")
    check("GET /api/model returns 200 on the ready path", r.status_code == 200)
    body = r.json()
    check("status is 'ready' when _ensure_model succeeds", body["status"] == "ready")
    check("active_model matches the mocked return", body["active_model"] == "qwen2.5:14b")
    check("primary_model matches Settings", body["primary_model"] == _expected.primary_model)
    check("fallback_model matches Settings", body["fallback_model"] == _expected.fallback_model)
    check("detail is absent on the ready path", body.get("detail") is None)


# ─── GET /api/model — unavailable path (Ollama down / model missing) ───

with patch(
    "api.app._brain._ensure_model",
    side_effect=RuntimeError("Ollama is not running. Start it with: ollama serve"),
):
    r = client.get("/api/model")
    check("GET /api/model still returns 200, not 500, when Ollama is down", r.status_code == 200)
    body = r.json()
    check("status is 'unavailable' when _ensure_model raises", body["status"] == "unavailable")
    check("active_model is None when unavailable", body["active_model"] is None)
    check("detail carries the RuntimeError message", "ollama" in body["detail"].lower())


if __name__ == "__main__":
    total = len(results)
    passed = sum(results)
    print(f"\n{passed}/{total} checks passed.")
    if passed != total:
        sys.exit(1)
    print("VEDA API — Step 1 (/status, /model) verified.")
