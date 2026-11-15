"""
Offline unit tests for Profile Verification, Ecosystem Platform Sync & Voice Silent Mode Override endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from interfaces.api.server import app

LOOPBACK = ("127.0.0.1", 50000)
client = TestClient(app, client=LOOPBACK)


def test_verify_code_send_and_check():
    # 1. Send Email Verification Code
    res = client.post("/api/profile/verify/send-code", json={"type": "email", "target": "dhanush@sam.local"})
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["target"] == "dhanush@sam.local"
    assert "123456" in data["code"]

    # 2. Check Valid Verification Code
    res_check = client.post(
        "/api/profile/verify/check-code",
        json={"type": "email", "target": "dhanush@sam.local", "code": "123456"}
    )
    assert res_check.status_code == 200
    assert res_check.json()["verified"] is True

    # 3. Invalid Code Rejection
    res_invalid = client.post(
        "/api/profile/verify/check-code",
        json={"type": "email", "target": "dhanush@sam.local", "code": "12"}
    )
    assert res_invalid.status_code == 400


def test_phone_verification_flow():
    # Send Phone SMS code
    res = client.post("/api/profile/verify/send-code", json={"type": "phone", "target": "+91 98765 43210"})
    assert res.status_code == 200
    assert res.json()["type"] == "phone"

    # Verify SMS code
    res_check = client.post(
        "/api/profile/verify/check-code",
        json={"type": "phone", "target": "+91 98765 43210", "code": "123456"}
    )
    assert res_check.status_code == 200
    assert res_check.json()["verified"] is True


def test_get_ecosystem_status():
    res = client.get("/api/profile/ecosystem")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "active"
    assert "telegram" in data["platforms"]
    assert "instagram" in data["platforms"]
    assert "whatsapp" in data["platforms"]
    assert "traceop" in data["platforms"]


def test_sync_ecosystem_and_traceop_persona():
    payload = {
        "platforms": [
            {"id": "telegram", "name": "Telegram", "handle": "@dhanush", "connected": True},
            {"id": "instagram", "name": "Instagram", "handle": "@dhanushsurada", "connected": True},
            {"id": "whatsapp", "name": "WhatsApp", "handle": "+91 98765 43210", "connected": True},
            {"id": "traceop", "name": "TraceOp", "handle": "traceop:usr_dhanush", "connected": True},
        ],
        "persona": {
            "overallScore": 96,
            "executiveSummary": "Sovereign systems architect and high-agency product builder.",
            "communicationStyle": "Direct, analytical, concise.",
            "activeHours": "08:00 - 02:00 IST",
            "keyInterests": ["Autonomous AI Systems", "Local LLMs"],
            "cognitivePreferences": ["First-principles reasoning"],
        },
        "user_id": "usr_sovereign_dhanush",
    }
    res = client.post("/api/profile/ecosystem/sync", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["synced_platforms"] == 4


def test_voice_silent_override_endpoint():
    res = client.post(
        "/api/voice/silent-override",
        json={"override_silent_mode": True, "volume_boost": 2.2}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["override_silent_mode"] is True
    assert data["volume_boost"] == 2.2
