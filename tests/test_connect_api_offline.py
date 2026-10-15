"""
OFFLINE test suite for /api/connect/* (interfaces/api/device_auth.py +
connect_routes.py + connect_schemas.py) — the FastAPI layer on top of the
connect/ subsystem tests/test_connect_offline.py already covers directly.

*** Could not be executed in the sandbox this branch was developed in ***
fastapi, pydantic, uvicorn and httpx are real project dependencies (see
requirements.txt) but were not installed in that sandbox, and it had no
network access to install them. tests/test_connect_offline.py — which
needs only `cryptography` and the stdlib — exercises every piece of logic
this file wires into HTTP (pairing, trust, revocation, signature
verification, capability validation, task routing/lifecycle, idempotency,
offline queueing, timeout sweep, handoff, the event bus) directly, and
77/77 of those checks pass. This file is written to the same standard and
the same conventions as tests/test_iqoo_phase1_offline.py's TestClient
usage, but run it for real — `pip install -r requirements.txt && python3
tests/test_connect_api_offline.py` — before treating it as passing.

Usage:
    HOME=/tmp/sam_connect_api_test python3 tests/test_connect_api_offline.py
"""

import asyncio
import base64
import json
import secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


def device_headers(private_key, device_id, method, path, body=b""):
    """What a real direct/LAN device's HTTP client sends on every
    authenticated request — see connect/transports/lan_http.py's module
    docstring for the four-header scheme this builds."""
    from connect.core import crypto
    from connect.transports import lan_http

    ts = str(time.time())
    nonce = secrets.token_urlsafe(16)
    message = lan_http.canonical_message(method, path, ts, nonce, body)
    sig = base64.b64encode(crypto.sign(private_key, message)).decode()
    return {
        "X-SAM-Device-Id": device_id,
        "X-SAM-Timestamp": ts,
        "X-SAM-Nonce": nonce,
        "X-SAM-Signature": sig,
    }


def main():
    from fastapi.testclient import TestClient

    import interfaces.api.server as server_module
    from interfaces.api.device_auth import reset_singletons_for_tests
    from connect.core import crypto

    reset_singletons_for_tests()
    # client=("127.0.0.1", ...) makes TestClient simulate a loopback caller
    # (its own default is the literal string "testclient", which
    # require_local_caller would correctly reject) — needed since this
    # branch's second pass added loopback-only restriction to every
    # desktop/Core-initiated /api/connect/* route (see connect_routes.py's
    # require_local_caller). If this constructor argument doesn't exist in
    # the installed fastapi/starlette version, every check below that hits
    # a protected route will fail with 403 — that's this assumption, not
    # the route logic, needing a fix.
    client = TestClient(server_module.app, client=("127.0.0.1", 12345))
    remote_client = TestClient(server_module.app, client=("192.168.1.222", 12345))

    # ─── Pairing ───────────────────────────────────────────────────────
    print("\n=== Pairing ===")
    r = client.post("/api/connect/pairing/start")
    check("POST /pairing/start returns 200", r.status_code == 200)
    qr = r.json()
    check("pairing payload has token/host/port", all(k in qr for k in ("token", "host", "port")))

    priv, pub = crypto.generate_keypair()
    pub_pem = crypto.serialize_public_key(pub)
    r = client.post("/api/connect/pairing/redeem", json={
        "token": qr["token"], "device_id": "api-test-phone", "device_name": "API Test Phone",
        "platform": "android", "public_key": pub_pem,
        "capabilities": {"app-launch": {"available": True, "permission": "granted"}},
    })
    check("POST /pairing/redeem returns 201", r.status_code == 201)
    check("redeem response reports trusted", r.json().get("status") == "trusted")

    r = client.post("/api/connect/pairing/redeem", json={
        "token": qr["token"], "device_id": "api-test-phone-2", "device_name": "Phone",
        "platform": "android", "public_key": pub_pem, "capabilities": {},
    })
    check("redeeming an already-used token returns 401", r.status_code == 401)

    r = client.post("/api/connect/pairing/redeem", json={
        "token": "garbage-token-never-issued", "device_id": "x", "device_name": "Phone",
        "platform": "android", "public_key": "not a real key", "capabilities": {},
    })
    check("a malformed public_key returns 422, not 500", r.status_code == 422)

    # ─── Local-caller restriction (desktop/Core-only routes) ────────────
    print("\n=== Local-caller restriction ===")
    r = remote_client.post("/api/connect/pairing/start")
    check("a non-loopback caller gets 403 on /pairing/start", r.status_code == 403)
    r = remote_client.get("/api/connect/devices")
    check("a non-loopback caller gets 403 on GET /devices", r.status_code == 403)
    r = remote_client.post("/api/connect/tasks", json={"target_device_id": "x", "action": "y"})
    check("a non-loopback caller gets 403 on POST /tasks", r.status_code == 403)
    r = remote_client.post("/api/connect/pairing/redeem", json={
        "token": "irrelevant", "device_id": "x", "device_name": "x",
        "platform": "android", "public_key": "x", "capabilities": {},
    })
    check("a non-loopback caller is NOT blocked on /pairing/redeem (device-facing, no loopback check)",
          r.status_code != 403)

    # ─── Devices ───────────────────────────────────────────────────────
    print("\n=== Devices ===")
    r = client.get("/api/connect/devices")
    check("GET /devices returns 200", r.status_code == 200)
    devices = r.json()
    check("the paired device appears in the list",
          any(d["external_id"] == "api-test-phone" for d in devices))
    internal_id = next(d["id"] for d in devices if d["external_id"] == "api-test-phone")

    r = client.post(f"/api/connect/devices/{internal_id}/rename", json={"name": "Renamed Phone"})
    check("POST /devices/{id}/rename returns 200", r.status_code == 200)
    r = client.get("/api/connect/devices")
    check("rename is reflected in the device list",
          any(d["device_name"] == "Renamed Phone" for d in r.json()))

    # ─── Device-authenticated endpoints ──────────────────────────────────
    print("\n=== Device-authenticated requests ===")
    path = "/api/connect/devices/api-test-phone/heartbeat"
    r = client.post(path, headers=device_headers(priv, "api-test-phone", "POST", path))
    check("a correctly signed heartbeat returns 200", r.status_code == 200)
    check("heartbeat response reports online", r.json().get("connection_state") == "online")
    check("heartbeat response includes pending_tasks (empty so far)", r.json().get("pending_tasks") == [])

    r = client.post(path)  # no auth headers at all
    check("a heartbeat with no auth headers returns 401", r.status_code == 401)

    other_priv, _ = crypto.generate_keypair()
    r = client.post(path, headers=device_headers(other_priv, "api-test-phone", "POST", path))
    check("a heartbeat signed with the wrong key returns 401", r.status_code == 401)

    # ─── Device tasks ────────────────────────────────────────────────────
    print("\n=== Device tasks ===")
    r = client.post("/api/connect/tasks", json={
        "target_device_id": "api-test-phone", "action": "open_app",
        "payload": {"package": "com.instagram.android"}, "required_capability": "app-launch",
    })
    check("POST /tasks (desktop-initiated) returns 201", r.status_code == 201)
    task = r.json()
    check("newly created task is dispatched (device is online)", task["status"] == "dispatched")
    task_id = task["task_id"]

    r = client.post("/api/connect/tasks", json={
        "target_device_id": "no-such-device", "action": "open_app",
    })
    check("routing to an unknown device returns 404", r.status_code == 404)

    r = client.post("/api/connect/tasks", json={
        "target_device_id": "api-test-phone", "action": "use_camera", "required_capability": "camera",
    })
    check("routing a missing capability returns 422", r.status_code == 422)

    ack_path = f"/api/connect/tasks/{task_id}/ack"
    r = client.post(ack_path, headers=device_headers(priv, "api-test-phone", "POST", ack_path))
    check("device-signed ack() returns 200", r.status_code == 200)
    check("ack() moves status to started", r.json()["status"] == "started")

    r = client.post(ack_path, headers=device_headers(other_priv, "api-test-phone", "POST", ack_path))
    check("a different key trying to ack the same device_id returns 401 (auth fails before ownership is even checked)",
          r.status_code == 401)

    complete_path = f"/api/connect/tasks/{task_id}/complete"
    # content=<exact bytes I sign> rather than json=<dict> — json= lets
    # httpx pick the serialization, which I can't verify byte-for-byte
    # without running it; content= sends exactly the bytes I compute the
    # signature over, so there is no ambiguity to flag here.
    complete_body = json.dumps({"result": {"opened": True}}).encode()
    r = client.post(complete_path, content=complete_body,
                     headers={"Content-Type": "application/json",
                              **device_headers(priv, "api-test-phone", "POST", complete_path, body=complete_body)})
    check("device-signed complete() (raw-bytes body, exact signature match) returns 200",
          r.status_code == 200)

    r = client.get(f"/api/connect/tasks/{task_id}")
    check("GET /tasks/{id} reflects the completed task", r.json()["status"] == "completed")

    r = client.get("/api/connect/tasks/no-such-task")
    check("GET /tasks/{id} for an unknown id returns 404", r.status_code == 404)

    # ─── Revocation cuts off device auth ────────────────────────────────
    print("\n=== Revocation ===")
    r = client.post(f"/api/connect/devices/{internal_id}/revoke")
    check("POST /devices/{id}/revoke returns 200", r.status_code == 200)
    r = client.post(path, headers=device_headers(priv, "api-test-phone", "POST", path))
    check("a revoked device's signed heartbeat now returns 401", r.status_code == 401)

    # ─── SSE event stream (tested as an async generator directly — same
    # reason interfaces/api/server.py's own event_stream() is factored out
    # for direct testing: no live HTTP connection needed) ────────────────
    print("\n=== Connect event stream ===")
    from interfaces.api.connect_routes import _connect_event_stream
    from interfaces.api.device_auth import get_event_bus

    get_event_bus().publish_to(["device:stream-test"], "device.connected", device_id="stream-test")

    async def _collect():
        chunks = []
        async for chunk in _connect_event_stream("device:stream-test", after_seq=0, request=None):
            chunks.append(chunk)
            if len(chunks) >= 1:
                break
        return chunks

    chunks = asyncio.run(_collect())
    check("the event stream yields the backlog as SSE-framed text",
          len(chunks) == 1 and chunks[0].startswith("id: 1\ndata: ") and "device.connected" in chunks[0])

    print(f"\n{'=' * 60}")
    passed = sum(1 for r in results if r)
    print(f"{passed}/{len(results)} checks passed")
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
