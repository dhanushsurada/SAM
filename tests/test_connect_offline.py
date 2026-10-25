"""
OFFLINE test suite for agent/cross-device (SAM Connect core + LAN
transport + task routing/handoff).

Everything here is offline and framework-free: no FastAPI, no real
Android device, no real network — exercises connect/core/device_registry.py,
connect/core/capabilities.py, connect/core/crypto.py, connect/core/events.py,
connect/transports/lan_http.py and connect/services/task_handoff.py
directly, the same way interfaces/api/*_offline.py test files exercise
TaskGateway/EventBus without a live HTTP server. interfaces/api/
device_auth.py, interfaces/api/connect_routes.py and interfaces/api/
connect_schemas.py are FastAPI-shaped wrappers around exactly this logic
and are NOT covered here — see tests/test_connect_api_offline.py, which
needs fastapi/pydantic/uvicorn/httpx installed to run (this file needs
only `cryptography`, already a project dependency, and the stdlib).

Usage:
    HOME=/tmp/sam_connect_test python3 tests/test_connect_offline.py
"""

import os
import sys
import tempfile
import atexit
import shutil
import base64
import secrets
import threading
import time
from pathlib import Path
from unittest import mock

if "sam_connect_test" not in os.environ.get("HOME", ""):
    _temp_home = tempfile.mkdtemp(prefix="sam_connect_test_")
    os.environ["HOME"] = _temp_home
    atexit.register(lambda: shutil.rmtree(_temp_home, ignore_errors=True))

sys.path.insert(0, str(Path(__file__).parent.parent))

from connect.core import crypto
from connect.core.capabilities import CapabilityValidationError, device_supports
from connect.core.device_registry import DIRECT_CHANNEL, DeviceRegistry
from connect.core.events import ConnectEventBus, UnknownEventTypeError
from connect.services.task_handoff import (
    CapabilityUnavailableError,
    DeviceTaskRouter,
    InvalidTaskStateError,
    TaskNotFoundError,
    TaskNotOwnedByDeviceError,
    UnknownDeviceError,
)
from connect.transports import lan_http

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


# ─── Helpers ───────────────────────────────────────────────────────────

def pair_device(registry, device_id, device_name="Test Phone", capabilities=None, port=8420):
    """Full pairing flow via the real public API (build_pairing_qr_payload
    + redeem_pairing) — returns (private_key, public_key_pem) so the
    caller can sign requests as this device."""
    private_key, public_key = crypto.generate_keypair()
    public_key_pem = crypto.serialize_public_key(public_key)
    qr = lan_http.build_pairing_qr_payload(registry, port=port)
    lan_http.redeem_pairing(registry, {
        "token": qr["token"], "device_id": device_id, "device_name": device_name,
        "platform": "android", "public_key": public_key_pem,
        "capabilities": capabilities or {},
    })
    return private_key, public_key_pem


def signed_request(private_key, device_id, method, path, body=b""):
    """Builds the four X-SAM-* header values a real client would send —
    returns (timestamp, nonce, signature_b64) ready to pass to
    verify_request."""
    ts = str(time.time())
    nonce = secrets.token_urlsafe(16)
    message = lan_http.canonical_message(method, path, ts, nonce, body)
    sig = base64.b64encode(crypto.sign(private_key, message)).decode()
    return ts, nonce, sig


def bring_online(registry, nonce_cache, private_key, device_id, path="/api/connect/devices/x/heartbeat"):
    """Simulates one successful authenticated request, which is what
    actually flips connection_state to 'online' (see
    DeviceRegistry.record_heartbeat's docstring)."""
    ts, nonce, sig = signed_request(private_key, device_id, "POST", path)
    return lan_http.verify_request(
        registry, nonce_cache, method="POST", path=path, body=b"",
        device_id=device_id, timestamp=ts, nonce=nonce, signature_b64=sig,
    )


# ─── Pairing & trust ─────────────────────────────────────────────────────

def test_pairing_and_trust():
    print("\n=== Pairing & Trust ===")
    registry = DeviceRegistry()
    priv, pub_pem = crypto.generate_keypair()
    pub_pem = crypto.serialize_public_key(pub_pem) if not isinstance(pub_pem, str) else pub_pem

    qr = lan_http.build_pairing_qr_payload(registry, port=8420)
    check("pairing payload has token/host/port/expires_at",
          all(k in qr for k in ("v", "token", "host", "port", "expires_at")))

    result = lan_http.redeem_pairing(registry, {
        "token": qr["token"], "device_id": "phone-1", "device_name": "Dhanush's Phone",
        "platform": "android", "public_key": pub_pem,
        "capabilities": {"voice": {"available": True, "permission": "granted"}},
    })
    check("redeem_pairing returns trusted status", result["status"] == "trusted")
    check("is_trusted true after pairing", registry.is_trusted("phone-1", channel=DIRECT_CHANNEL))

    device = registry.get_device_by_external_id("phone-1", channel=DIRECT_CHANNEL)
    check("device dict has parsed capabilities", device["capabilities"].get("voice", {}).get("available") is True)
    check("device starts offline until first heartbeat", device["connection_state"] == "offline")

    # Re-using the same token a second time must fail (one-time use)
    reused = registry.redeem_token(qr["token"], "phone-2", channel=DIRECT_CHANNEL)
    check("a redeemed token cannot be reused", reused is False)

    # An unknown/garbage token must fail cleanly, not raise
    bogus = registry.redeem_token("not-a-real-token", "phone-3", channel=DIRECT_CHANNEL)
    check("a bogus token is rejected, not raised", bogus is False)


def test_revocation_and_repairing():
    print("\n=== Revocation & Re-pairing ===")
    registry = DeviceRegistry()
    priv, pub_pem = crypto.generate_keypair()
    pub_pem = crypto.serialize_public_key(pub_pem)
    qr = lan_http.build_pairing_qr_payload(registry, port=8420)
    lan_http.redeem_pairing(registry, {
        "token": qr["token"], "device_id": "revoke-me", "device_name": "Phone",
        "platform": "android", "public_key": pub_pem, "capabilities": {},
    })
    internal_id = next(d["id"] for d in registry.list_devices(include_pending=True)
                        if d["external_id"] == "revoke-me")

    check("revoke() succeeds on a trusted device", registry.revoke(internal_id))
    check("is_trusted false after revoke", not registry.is_trusted("revoke-me", channel=DIRECT_CHANNEL))
    check("revoking again returns False (already revoked)", registry.revoke(internal_id) is False)

    # This is the regression test for a real bug found while writing this
    # suite: redeem_token's "does a row already exist" check originally
    # only matched status='trusted', so a *revoked* row was invisible to
    # it and a fresh pairing attempt for the same external_id crashed with
    # a sqlite3.IntegrityError on UNIQUE(channel, external_id) instead of
    # ever returning True/False. Fixed in this branch (see
    # connect/core/device_registry.py's redeem_token, "Does a row for this
    # (channel, external_id) already exist" comment).
    qr2 = lan_http.build_pairing_qr_payload(registry, port=8420)
    try:
        result2 = lan_http.redeem_pairing(registry, {
            "token": qr2["token"], "device_id": "revoke-me", "device_name": "Phone (reinstalled)",
            "platform": "android", "public_key": pub_pem,
            "capabilities": {"camera": {"available": True, "permission": "granted"}},
        })
        check("re-pairing a revoked device no longer raises", True)
        check("re-pairing a revoked device restores trust", result2["status"] == "trusted")
    except Exception as e:
        check(f"re-pairing a revoked device no longer raises (got {type(e).__name__}: {e})", False)
        check("re-pairing a revoked device restores trust", False)

    device = registry.get_device_by_external_id("revoke-me", channel=DIRECT_CHANNEL)
    check("re-paired device has refreshed name", device is not None and device["device_name"] == "Phone (reinstalled)")
    check("re-paired device has refreshed capabilities",
          device is not None and device_supports(device["capabilities"], "camera"))

    with __import__("sqlite3").connect(registry.db_path()) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM devices WHERE channel = ? AND external_id = ?",
            (DIRECT_CHANNEL, "revoke-me"),
        ).fetchone()[0]
    check("exactly one row remains for this external_id (no orphaned duplicate)", n == 1)

    check("rename() succeeds on the re-trusted device", registry.rename(internal_id, "Dhanush's iQOO"))
    check("rename() reflected in list_devices",
          any(d["device_name"] == "Dhanush's iQOO" for d in registry.list_devices()))


# ─── Signed-request verification ────────────────────────────────────────

def test_signature_verification():
    print("\n=== Signed request verification (connect/transports/lan_http.py) ===")
    registry = DeviceRegistry()
    priv, pub_pem = crypto.generate_keypair()
    pub_pem = crypto.serialize_public_key(pub_pem)
    qr = lan_http.build_pairing_qr_payload(registry, port=8420)
    lan_http.redeem_pairing(registry, {
        "token": qr["token"], "device_id": "sig-test", "device_name": "Phone",
        "platform": "android", "public_key": pub_pem, "capabilities": {},
    })
    nonce_cache = lan_http.NonceCache()
    method, path, body = "POST", "/api/connect/tasks/abc/ack", b""

    ts, nonce, sig = signed_request(priv, "sig-test", method, path, body)
    device = lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                      device_id="sig-test", timestamp=ts, nonce=nonce, signature_b64=sig)
    check("a correctly signed request verifies", device["external_id"] == "sig-test")
    check("verify_request flips connection_state to online", device["connection_state"] == "online")

    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                 device_id="sig-test", timestamp=ts, nonce=nonce, signature_b64=sig)
        check("a byte-for-byte replay is rejected", False)
    except lan_http.ReplayedRequestError:
        check("a byte-for-byte replay is rejected", True)

    ts2, nonce2, sig2 = signed_request(priv, "sig-test", method, path, body)
    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=b"different body",
                                 device_id="sig-test", timestamp=ts2, nonce=nonce2, signature_b64=sig2)
        check("a tampered body is rejected", False)
    except lan_http.InvalidSignatureError:
        check("a tampered body is rejected", True)

    other_priv, _ = crypto.generate_keypair()
    ts3, nonce3, wrong_sig = signed_request(other_priv, "sig-test", method, path, body)
    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                 device_id="sig-test", timestamp=ts3, nonce=nonce3, signature_b64=wrong_sig)
        check("a signature from the wrong key is rejected", False)
    except lan_http.InvalidSignatureError:
        check("a signature from the wrong key is rejected", True)

    old_ts = str(time.time() - lan_http.TIMESTAMP_WINDOW_SECONDS - 30)
    nonce4 = secrets.token_urlsafe(16)
    msg = lan_http.canonical_message(method, path, old_ts, nonce4, body)
    old_sig = base64.b64encode(crypto.sign(priv, msg)).decode()
    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                 device_id="sig-test", timestamp=old_ts, nonce=nonce4, signature_b64=old_sig)
        check("a stale timestamp outside the window is rejected", False)
    except lan_http.TimestampOutOfRangeError:
        check("a stale timestamp outside the window is rejected", True)

    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                 device_id=None, timestamp=None, nonce=None, signature_b64=None)
        check("missing credentials are rejected", False)
    except lan_http.MissingCredentialsError:
        check("missing credentials are rejected", True)

    ts5, nonce5, sig5 = signed_request(priv, "never-paired", method, path, body)
    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                 device_id="never-paired", timestamp=ts5, nonce=nonce5, signature_b64=sig5)
        check("an unpaired device_id is rejected", False)
    except lan_http.DeviceNotTrustedError:
        check("an unpaired device_id is rejected", True)

    # A revoked device must fail auth too, not just "trust-gated" lookups
    internal_id = next(d["id"] for d in registry.list_devices() if d["external_id"] == "sig-test")
    registry.revoke(internal_id)
    ts6, nonce6, sig6 = signed_request(priv, "sig-test", method, path, body)
    try:
        lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                 device_id="sig-test", timestamp=ts6, nonce=nonce6, signature_b64=sig6)
        check("a revoked device fails signed-request auth", False)
    except lan_http.DeviceNotTrustedError:
        check("a revoked device fails signed-request auth", True)


# ─── Capability model ────────────────────────────────────────────────────

def test_capabilities():
    print("\n=== Capability model (connect/core/capabilities.py) ===")
    registry = DeviceRegistry()
    try:
        registry.redeem_token(
            registry.create_pairing_token(channel=DIRECT_CHANNEL), "cap-test", channel=DIRECT_CHANNEL,
            platform="android", public_key=crypto.serialize_public_key(crypto.generate_keypair()[1]),
            capabilities={"not-a-real-capability": {"available": True, "permission": "granted"}},
        )
        check("an unknown capability name is rejected", False)
    except CapabilityValidationError:
        check("an unknown capability name is rejected", True)

    try:
        registry.redeem_token(
            registry.create_pairing_token(channel=DIRECT_CHANNEL), "cap-test-2", channel=DIRECT_CHANNEL,
            platform="android", public_key=crypto.serialize_public_key(crypto.generate_keypair()[1]),
            capabilities={"camera": {"available": "yes", "permission": "granted"}},
        )
        check("a non-boolean 'available' is rejected", False)
    except CapabilityValidationError:
        check("a non-boolean 'available' is rejected", True)

    normalized = None
    from connect.core.capabilities import validate_capabilities
    normalized = validate_capabilities({"camera": {"available": False, "permission": "granted"}})
    check("available=False forces permission back to not_requested",
          normalized["camera"]["permission"] == "not_requested")

    caps = {"app-launch": {"available": True, "permission": "granted"},
            "camera": {"available": True, "permission": "denied"}}
    check("device_supports true for available+granted", device_supports(caps, "app-launch") is True)
    check("device_supports false for available+denied", device_supports(caps, "camera") is False)
    check("device_supports false for a capability never reported", device_supports(caps, "voice") is False)


# ─── Task routing & lifecycle ───────────────────────────────────────────

def test_task_lifecycle():
    print("\n=== Device task routing & lifecycle (connect/services/task_handoff.py) ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    nonce_cache = lan_http.NonceCache()

    priv, pub_pem = pair_device(registry, "d-online",
                                 capabilities={"app-launch": {"available": True, "permission": "granted"}})
    bring_online(registry, nonce_cache, priv, "d-online")

    try:
        router.create(origin="desktop", target_device_id="does-not-exist", action="open_app")
        check("routing to an unknown device raises UnknownDeviceError", False)
    except UnknownDeviceError:
        check("routing to an unknown device raises UnknownDeviceError", True)

    try:
        router.create(origin="desktop", target_device_id="d-online", action="use_camera",
                       required_capability="camera")
        check("routing a missing capability raises CapabilityUnavailableError", False)
    except CapabilityUnavailableError:
        check("routing a missing capability raises CapabilityUnavailableError", True)

    task = router.create(origin="desktop", target_device_id="d-online", action="open_app",
                          payload={"package": "com.instagram.android"}, required_capability="app-launch")
    check("task dispatched immediately when device is online", task.status == "dispatched")

    try:
        router.ack(task.task_id, "some-other-device")
        check("a different device acking the task raises TaskNotOwnedByDeviceError", False)
    except TaskNotOwnedByDeviceError:
        check("a different device acking the task raises TaskNotOwnedByDeviceError", True)

    task = router.ack(task.task_id, "d-online")
    check("ack() moves status to started", task.status == "started")
    task = router.progress(task.task_id, "d-online", "opening Instagram", pct=40)
    check("progress() moves status to in_progress", task.status == "in_progress")
    task = router.action(task.task_id, "d-online", "tapped the Instagram icon")
    check("action() keeps status in_progress", task.status == "in_progress")
    task = router.verification(task.task_id, "d-online", verified=True, detail="app is in foreground")
    check("verification() does not itself complete the task", task.status == "in_progress")
    task = router.complete(task.task_id, "d-online", result={"opened": True})
    check("complete() moves status to completed", task.status == "completed")
    check("complete() stores the result", task.result == {"opened": True})

    try:
        router.progress(task.task_id, "d-online", "too late")
        check("updating a terminal task raises InvalidTaskStateError", False)
    except InvalidTaskStateError:
        check("updating a terminal task raises InvalidTaskStateError", True)

    task_events = events.get_since(f"task:{task.task_id}")
    event_types = [e["type"] for e in task_events]
    check("full event sequence published for the task",
          event_types == ["task.created", "task.progress", "task.started", "task.progress",
                           "task.action", "task.verification", "task.completed"])

    # fail()
    task2 = router.create(origin="desktop", target_device_id="d-online", action="open_app",
                           required_capability="app-launch")
    router.ack(task2.task_id, "d-online")
    task2 = router.fail(task2.task_id, "d-online", "app crashed on launch")
    check("fail() moves status to failed", task2.status == "failed")
    check("fail() stores the error", task2.error == "app crashed on launch")

    # cancel() — initiator-side, not device-side
    task3 = router.create(origin="desktop", target_device_id="d-online", action="open_app",
                           required_capability="app-launch")
    cancelled = router.cancel(task3.task_id, reason="user changed their mind")
    check("cancel() returns True for a non-terminal task", cancelled is True)
    check("cancel() moves status to cancelled", router.get(task3.task_id).status == "cancelled")
    check("cancelling an already-terminal task returns False, not an error",
          router.cancel(task3.task_id) is False)

    try:
        router.get("no-such-task-id")
        check("get() on an unknown task_id raises TaskNotFoundError", False)
    except TaskNotFoundError:
        check("get() on an unknown task_id raises TaskNotFoundError", True)


def test_idempotency():
    print("\n=== Idempotency ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    pair_device(registry, "d-idem", capabilities={"app-launch": {"available": True, "permission": "granted"}})

    t1 = router.create(origin="desktop", target_device_id="d-idem", action="open_app",
                        idempotency_key="retry-key-1")
    t2 = router.create(origin="desktop", target_device_id="d-idem", action="open_app",
                        idempotency_key="retry-key-1")
    check("two create() calls with the same idempotency_key return the same task",
          t1.task_id == t2.task_id)

    t3 = router.create(origin="desktop", target_device_id="d-idem", action="open_app",
                        idempotency_key="retry-key-2")
    check("a different idempotency_key creates a distinct task", t3.task_id != t1.task_id)


def test_offline_queueing_and_redelivery():
    print("\n=== Offline queueing & redelivery on reconnect ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    nonce_cache = lan_http.NonceCache()
    priv, _ = pair_device(registry, "d-offline",
                           capabilities={"app-launch": {"available": True, "permission": "granted"}})

    task = router.create(origin="desktop", target_device_id="d-offline", action="open_app",
                          required_capability="app-launch")
    check("task queued (not dispatched) while device has never connected",
          task.status == "queued_offline")

    bring_online(registry, nonce_cache, priv, "d-offline")
    pending = router.get_pending_for_device("d-offline")
    check("get_pending_for_device returns the queued task", len(pending) == 1 and pending[0].task_id == task.task_id)
    check("get_pending_for_device redelivers it (queued_offline -> dispatched)",
          pending[0].status == "dispatched")
    check("the redelivery is persisted, not just in the returned copy",
          router.get(task.task_id).status == "dispatched")


def test_timeout_sweep():
    print("\n=== Timeout sweep ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    pair_device(registry, "d-timeout", capabilities={"app-launch": {"available": True, "permission": "granted"}})

    task = router.create(origin="desktop", target_device_id="d-timeout", action="open_app",
                          required_capability="app-launch", timeout_seconds=1)
    from datetime import datetime, timedelta
    future = datetime.now() + timedelta(seconds=5)
    timed_out = router.sweep_timeouts(now=future)
    check("a task past its timeout_seconds is swept", any(t.task_id == task.task_id for t in timed_out))
    check("a timed-out task's status is timed_out", router.get(task.task_id).status == "timed_out")

    fresh_task = router.create(origin="desktop", target_device_id="d-timeout", action="open_app",
                                required_capability="app-launch", timeout_seconds=600)
    timed_out2 = router.sweep_timeouts(now=datetime.now())
    check("a task well within its timeout is not swept",
          not any(t.task_id == fresh_task.task_id for t in timed_out2))


def test_handoff():
    print("\n=== Context handoff ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    nonce_cache = lan_http.NonceCache()
    priv_a, _ = pair_device(registry, "device-a",
                             capabilities={"app-launch": {"available": True, "permission": "granted"}})
    priv_b, _ = pair_device(registry, "device-b",
                             capabilities={"app-launch": {"available": True, "permission": "granted"}})
    bring_online(registry, nonce_cache, priv_a, "device-a")
    bring_online(registry, nonce_cache, priv_b, "device-b")

    original = router.create(origin="desktop", target_device_id="device-a", action="continue_chat",
                              payload={"topic": "dinner plans"}, context_ref="conv-42",
                              handoff_state={"last_message_id": 17})
    router.ack(original.task_id, "device-a")

    handed_off = router.handoff(original.task_id, "device-b", reason="user switched to their phone")
    check("handoff() creates a new task targeting the new device",
          handed_off.target_device_id == "device-b")
    check("handoff() links back via handoff_of", handed_off.handoff_of == original.task_id)
    check("handoff() carries context_ref across unchanged", handed_off.context_ref == "conv-42")
    check("handoff() carries handoff_state across unchanged",
          handed_off.handoff_state == {"last_message_id": 17})
    check("the original task is cancelled by the handoff",
          router.get(original.task_id).status == "cancelled")
    check("the original task's event history is still queryable",
          len(events.get_since(f"task:{original.task_id}")) > 0)


# ─── sweep_offline (connection-state transitions) ───────────────────────

def test_sweep_offline():
    print("\n=== sweep_offline (connect/core/device_registry.py) ===")
    registry = DeviceRegistry()
    nonce_cache = lan_http.NonceCache()
    priv, _ = pair_device(registry, "d-flaky")
    bring_online(registry, nonce_cache, priv, "d-flaky")
    device = registry.get_device_by_external_id("d-flaky", channel=DIRECT_CHANNEL)
    check("device is online right after a verified request", device["connection_state"] == "online")

    transitioned = registry.sweep_offline(stale_after_seconds=-1)  # everything looks "stale"
    check("sweep_offline with a negative staleness flips the online device",
          any(d["external_id"] == "d-flaky" for d in transitioned))
    device = registry.get_device_by_external_id("d-flaky", channel=DIRECT_CHANNEL)
    check("device reads back offline after the sweep", device["connection_state"] == "offline")

    transitioned2 = registry.sweep_offline(stale_after_seconds=-1)
    check("sweeping an already-offline device is not reported as a fresh transition",
          not any(d["external_id"] == "d-flaky" for d in transitioned2))

    # Telegram-channel rows must never be reported by sweep_offline/read as
    # anything but "n/a" — they never heartbeat, so "offline" would be
    # actively misleading (see connection_state_for's own docstring).
    registry.redeem_token(registry.create_pairing_token(channel="telegram"), "12345", channel="telegram")
    tg_devices = [d for d in registry.list_devices() if d["channel"] == "telegram"]
    check("a Telegram-channel device reads connection_state as n/a, not offline",
          all(d["connection_state"] == "n/a" for d in tg_devices))


# ─── ConnectEventBus itself ─────────────────────────────────────────────

def test_event_bus():
    print("\n=== ConnectEventBus (connect/core/events.py) ===")
    events = ConnectEventBus()

    try:
        events.publish("device", "not.a.real.event.type")
        check("publishing an unknown event type raises UnknownEventTypeError", False)
    except UnknownEventTypeError:
        check("publishing an unknown event type raises UnknownEventTypeError", True)

    e1 = events.publish_to(["device:x", "device"], "device.connected", device_id="x")
    check("publish_to publishes to every listed stream", len(e1) == 2 and all(e1))
    check("each stream gets its own independent seq number",
          events.get_since("device:x")[0]["seq"] == 1 and events.get_since("device")[0]["seq"] == 1)

    events.publish("task:abc", "task.created", task_id="abc")
    events.publish("task:abc", "task.completed", task_id="abc", result={})
    check("has_terminal_event true after a terminal task event", events.has_terminal_event("task:abc"))
    ignored = events.publish("task:abc", "task.progress", task_id="abc", message="too late")
    check("publishing after a terminal event is silently ignored, not raised", ignored is None)
    check("the ignored event did not get appended to history", len(events.get_since("task:abc")) == 2)

    check("get_since respects after_seq", len(events.get_since("task:abc", after_seq=1)) == 1)


# ─── Adversarial signature tampering (hardening pass) ───────────────────

def test_crypto_adversarial():
    print("\n=== Adversarial signature tampering (hardening pass) ===")
    registry = DeviceRegistry()
    nonce_cache = lan_http.NonceCache()
    priv_a, pub_a = crypto.generate_keypair()
    priv_b, pub_b = crypto.generate_keypair()
    lan_http.redeem_pairing(registry, {
        "token": lan_http.build_pairing_qr_payload(registry, port=8420)["token"],
        "device_id": "adv-a", "device_name": "A", "platform": "android",
        "public_key": crypto.serialize_public_key(pub_a), "capabilities": {},
    })
    lan_http.redeem_pairing(registry, {
        "token": lan_http.build_pairing_qr_payload(registry, port=8420)["token"],
        "device_id": "adv-b", "device_name": "B", "platform": "android",
        "public_key": crypto.serialize_public_key(pub_b), "capabilities": {},
    })

    def try_verify(method, path, body, device_id, ts, nonce, sig_b64, label):
        try:
            lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                     device_id=device_id, timestamp=ts, nonce=nonce, signature_b64=sig_b64)
            check(label, False)
        except lan_http.DeviceAuthError:
            check(label, True)

    base_method, base_path, base_body = "POST", "/api/connect/tasks/t1/ack", b""

    # 1. Valid request — the control case; everything below is a mutation of this
    ts0, nonce0, sig0 = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    device = lan_http.verify_request(registry, nonce_cache, method=base_method, path=base_path, body=base_body,
                                      device_id="adv-a", timestamp=ts0, nonce=nonce0, signature_b64=sig0)
    check("1. valid request verifies", device["external_id"] == "adv-a")

    # 2. Modified HTTP method after signing
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify("GET", base_path, base_body, "adv-a", ts, nonce, sig,
               "2. signature does not cover a method swapped after signing")

    # 3. Modified path after signing
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify(base_method, "/api/connect/tasks/t1/complete", base_body, "adv-a", ts, nonce, sig,
               "3. signature does not cover a path swapped after signing")

    # 4. Modified timestamp after signing (not just "stale" — a byte-for-byte
    # different, still-in-window timestamp the attacker substitutes)
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    ts_shifted = str(float(ts) + 1)
    try_verify(base_method, base_path, base_body, "adv-a", ts_shifted, nonce, sig,
               "4. signature does not cover a timestamp swapped after signing")

    # 5. Modified nonce after signing
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify(base_method, base_path, base_body, "adv-a", ts, secrets.token_urlsafe(16), sig,
               "5. signature does not cover a nonce swapped after signing")

    # 6. Modified body after signing (already covered in test_signature_verification
    # as "tampered body" — repeated here as part of the complete adversarial matrix)
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify(base_method, base_path, b"a different body entirely", "adv-a", ts, nonce, sig,
               "6. signature does not cover a body swapped after signing")

    # 7. Modified device ID — claims to be device B while signed by A's key.
    # B is a real, trusted device (unlike the "unpaired device_id" case
    # test_signature_verification already covers), so this specifically
    # proves cross-device signature substitution fails, not just "unknown
    # device_id" failing.
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify(base_method, base_path, base_body, "adv-b", ts, nonce, sig,
               "7. A's signature does not verify against B's stored key")

    # 8. Corrupted/modified signature bytes (flip the last byte)
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    corrupted = base64.b64encode(base64.b64decode(sig)[:-1] + bytes([base64.b64decode(sig)[-1] ^ 0xFF])).decode()
    try_verify(base_method, base_path, base_body, "adv-a", ts, nonce, corrupted,
               "8. a bit-flipped signature is rejected")

    # 9. Signature is well-formed base64 but not a valid Ed25519 signature at all
    garbage_sig = base64.b64encode(b"not a real signature, wrong length").decode()
    ts, nonce, _ = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify(base_method, base_path, base_body, "adv-a", ts, nonce, garbage_sig,
               "9. a structurally invalid signature is rejected, not a 500")

    # 10. Missing auth headers — already covered in test_signature_verification;
    # confirmed here too as part of the complete matrix
    try_verify(base_method, base_path, base_body, None, None, None, None,
               "10. missing credentials rejected (adversarial matrix)")

    # 11. Stale timestamp — already covered in test_signature_verification
    old_ts = str(time.time() - lan_http.TIMESTAMP_WINDOW_SECONDS - 30)
    nonce_old = secrets.token_urlsafe(16)
    msg = lan_http.canonical_message(base_method, base_path, old_ts, nonce_old, base_body)
    old_sig = base64.b64encode(crypto.sign(priv_a, msg)).decode()
    try_verify(base_method, base_path, base_body, "adv-a", old_ts, nonce_old, old_sig,
               "11. stale timestamp rejected (adversarial matrix)")

    # 12. Replayed nonce — already covered in test_signature_verification
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    lan_http.verify_request(registry, nonce_cache, method=base_method, path=base_path, body=base_body,
                             device_id="adv-a", timestamp=ts, nonce=nonce, signature_b64=sig)
    try_verify(base_method, base_path, base_body, "adv-a", ts, nonce, sig,
               "12. replayed (device_id, nonce) rejected (adversarial matrix)")

    # 13. Unpaired device
    ts, nonce, sig = signed_request(priv_a, "never-paired-adv", base_method, base_path, base_body)
    try_verify(base_method, base_path, base_body, "never-paired-adv", ts, nonce, sig,
               "13. unpaired device rejected (adversarial matrix)")

    # 14. Revoked device
    internal_id = next(d["id"] for d in registry.list_devices() if d["external_id"] == "adv-b")
    registry.revoke(internal_id)
    ts, nonce, sig = signed_request(priv_b, "adv-b", base_method, base_path, base_body)
    try_verify(base_method, base_path, base_body, "adv-b", ts, nonce, sig,
               "14. revoked device rejected (adversarial matrix)")

    # 15. Corrupted stored public key — simulates DB corruption/bit-rot, not
    # an attacker-controlled input. Must fail closed (a DeviceAuthError,
    # i.e. 401 once wired to HTTP), never an unhandled exception (500).
    with __import__("sqlite3").connect(registry.db_path()) as conn:
        conn.execute("UPDATE devices SET public_key = ? WHERE channel = ? AND external_id = ?",
                     ("this is not a PEM-encoded public key", DIRECT_CHANNEL, "adv-a"))
        conn.commit()
    ts, nonce, sig = signed_request(priv_a, "adv-a", base_method, base_path, base_body)
    try_verify(base_method, base_path, base_body, "adv-a", ts, nonce, sig,
               "15. corrupted stored public key fails closed, not a crash")


# ─── Pairing security (hardening pass) ───────────────────────────────────

def test_pairing_security_extra():
    print("\n=== Pairing security, extra cases (hardening pass) ===")
    registry = DeviceRegistry()

    # Expired token
    token = registry.create_pairing_token(channel=DIRECT_CHANNEL)
    with __import__("sqlite3").connect(registry.db_path()) as conn:
        conn.execute(
            "UPDATE devices SET token_expires_at = ? WHERE pairing_token = ?",
            ((__import__("datetime").datetime.now() - __import__("datetime").timedelta(minutes=1)).isoformat(), token),
        )
        conn.commit()
    ok = registry.redeem_token(token, "expired-test", channel=DIRECT_CHANNEL)
    check("an expired pairing token is rejected", ok is False)
    check("an expired token is consumed (not left redeemable after the check)",
          registry.redeem_token(token, "expired-test-2", channel=DIRECT_CHANNEL) is False)

    # Wrong channel: a token minted for "telegram" must not redeem on "direct"
    tg_token = registry.create_pairing_token(channel="telegram")
    wrong_channel_ok = registry.redeem_token(tg_token, "wrong-channel-device", channel=DIRECT_CHANNEL)
    check("a telegram-channel token cannot be redeemed on the direct channel", wrong_channel_ok is False)
    # ... and the reverse
    direct_token = registry.create_pairing_token(channel=DIRECT_CHANNEL)
    wrong_channel_ok2 = registry.redeem_token(direct_token, "12345", channel="telegram")
    check("a direct-channel token cannot be redeemed on the telegram channel", wrong_channel_ok2 is False)
    # the direct_token is still valid for its real channel (proves the
    # rejection above didn't consume it)
    check("the direct-channel token still redeems correctly on its own channel",
          registry.redeem_token(direct_token, "right-channel-device", channel=DIRECT_CHANNEL) is True)

    # A second, FRESH token (not a reuse of the same one) for an
    # ALREADY-trusted external_id should reconcile into the existing row,
    # not collide/crash — this is the "already trusted" branch of the fix
    # documented in test_revocation_and_repairing, exercised here via a
    # genuinely new token rather than the revoked-device path.
    priv, pub_pem = crypto.generate_keypair()
    pub_pem = crypto.serialize_public_key(pub_pem)
    first = lan_http.build_pairing_qr_payload(registry, port=8420)
    lan_http.redeem_pairing(registry, {
        "token": first["token"], "device_id": "already-trusted-dev", "device_name": "First name",
        "platform": "android", "public_key": pub_pem, "capabilities": {},
    })
    second = lan_http.build_pairing_qr_payload(registry, port=8420)
    try:
        result = lan_http.redeem_pairing(registry, {
            "token": second["token"], "device_id": "already-trusted-dev", "device_name": "Second name",
            "platform": "android", "public_key": pub_pem,
            "capabilities": {"voice": {"available": True, "permission": "granted"}},
        })
        check("a second fresh token for an already-trusted device does not crash", True)
        check("...and still reports trusted", result["status"] == "trusted")
    except Exception as e:
        check(f"a second fresh token for an already-trusted device does not crash (got {type(e).__name__}: {e})", False)
    device = registry.get_device_by_external_id("already-trusted-dev", channel=DIRECT_CHANNEL)
    check("...and refreshes capabilities from the new redemption",
          device is not None and device_supports(device["capabilities"], "voice"))


# ─── Task state machine (hardening pass) ─────────────────────────────────

def test_state_machine_transitions():
    print("\n=== Task state machine — invalid transitions (hardening pass) ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    nonce_cache = lan_http.NonceCache()
    priv, _ = pair_device(registry, "sm-1", capabilities={"app-launch": {"available": True, "permission": "granted"}})
    bring_online(registry, nonce_cache, priv, "sm-1")

    # cancelled -> started MUST FAIL (cancel() is terminal)
    t = router.create(origin="desktop", target_device_id="sm-1", action="open_app",
                       required_capability="app-launch")
    router.cancel(t.task_id)
    try:
        router.ack(t.task_id, "sm-1")
        check("cancelled -> started fails", False)
    except InvalidTaskStateError:
        check("cancelled -> started fails", True)

    # timed_out -> completed MUST FAIL
    t2 = router.create(origin="desktop", target_device_id="sm-1", action="open_app",
                        required_capability="app-launch", timeout_seconds=1)
    from datetime import datetime, timedelta
    router.sweep_timeouts(now=datetime.now() + timedelta(seconds=5))
    check("task is timed_out after the sweep", router.get(t2.task_id).status == "timed_out")
    try:
        router.complete(t2.task_id, "sm-1", result={})
        check("timed_out -> completed fails", False)
    except InvalidTaskStateError:
        check("timed_out -> completed fails", True)

    # completed -> failed MUST FAIL (distinct from the existing
    # completed -> progress check in test_task_lifecycle)
    t3 = router.create(origin="desktop", target_device_id="sm-1", action="open_app",
                        required_capability="app-launch")
    router.ack(t3.task_id, "sm-1")
    router.complete(t3.task_id, "sm-1", result={})
    try:
        router.fail(t3.task_id, "sm-1", "too late")
        check("completed -> failed fails", False)
    except InvalidTaskStateError:
        check("completed -> failed fails", True)

    # failed -> completed MUST FAIL
    t4 = router.create(origin="desktop", target_device_id="sm-1", action="open_app",
                        required_capability="app-launch")
    router.ack(t4.task_id, "sm-1")
    router.fail(t4.task_id, "sm-1", "boom")
    try:
        router.complete(t4.task_id, "sm-1", result={})
        check("failed -> completed fails", False)
    except InvalidTaskStateError:
        check("failed -> completed fails", True)

    # cancelling an already-cancelled/terminal task never raises — returns
    # False (already covered in test_task_lifecycle; not repeated here)

    # FINDING, not a bug fix: the pre-existing (unmodified by this branch)
    # guard is "not already terminal", not "must currently be started" —
    # so complete()/progress()/action()/verification() are all reachable
    # directly from "dispatched", skipping ack() entirely. Ownership is
    # still checked (a device can only complete its own task), so this is
    # not a trust/security gap, but it IS looser than the state diagram in
    # docs/architecture/CROSS_DEVICE_PROTOCOL.md section 8 depicts. Recorded
    # here as documented, verified behavior — not silently tightened,
    # per this pass's own instruction not to change the state machine
    # without a concrete defect requiring it (this isn't one: ownership
    # still gates it, and a device that can genuinely complete a trivial
    # action instantly has no obvious reason to be forced through an extra
    # ack() round-trip first).
    t5 = router.create(origin="desktop", target_device_id="sm-1", action="open_app",
                        required_capability="app-launch")
    check("t5 is dispatched (not started) before this check", t5.status == "dispatched")
    t5_completed = router.complete(t5.task_id, "sm-1", result={"instant": True})
    check("FINDING: dispatched -> completed is allowed, skipping ack() "
          "(ownership-checked, not a security gap — see comment above)",
          t5_completed.status == "completed")

# ─── Multi-hop handoff (hardening pass) ──────────────────────────────────

def test_handoff_multi_hop():
    print("\n=== Multi-hop handoff A -> B -> C (hardening pass) ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    nonce_cache = lan_http.NonceCache()
    caps = {"app-launch": {"available": True, "permission": "granted"}}
    priv_a, _ = pair_device(registry, "hop-a", capabilities=caps)
    priv_b, _ = pair_device(registry, "hop-b", capabilities=caps)
    priv_c, _ = pair_device(registry, "hop-c", capabilities=caps)
    for priv, dev in ((priv_a, "hop-a"), (priv_b, "hop-b"), (priv_c, "hop-c")):
        bring_online(registry, nonce_cache, priv, dev)

    original = router.create(origin="desktop", target_device_id="hop-a", action="continue_chat",
                              context_ref="conv-99", handoff_state={"step": 1})
    router.ack(original.task_id, "hop-a")
    a_to_b = router.handoff(original.task_id, "hop-b", reason="switching devices")
    check("A->B targets device B", a_to_b.target_device_id == "hop-b")
    check("A->B links back to the original", a_to_b.handoff_of == original.task_id)
    router.ack(a_to_b.task_id, "hop-b")
    b_to_c = router.handoff(a_to_b.task_id, "hop-c", reason="switching again")
    check("B->C targets device C", b_to_c.target_device_id == "hop-c")
    check("B->C links back to the B leg, not the original A leg directly",
          b_to_c.handoff_of == a_to_b.task_id)
    check("context_ref survives two hops unchanged", b_to_c.context_ref == "conv-99")
    check("handoff_state survives two hops unchanged", b_to_c.handoff_state == {"step": 1})
    check("the A leg is cancelled", router.get(original.task_id).status == "cancelled")
    check("the B leg is cancelled", router.get(a_to_b.task_id).status == "cancelled")
    check("the C leg is still active", router.get(b_to_c.task_id).status in ("dispatched", "started"))
    check("the full lineage is reconstructable by following handoff_of",
          router.get(b_to_c.task_id).handoff_of == a_to_b.task_id
          and router.get(a_to_b.task_id).handoff_of == original.task_id)
    check("the original task's event history is still queryable after two hops",
          len(events.get_since(f"task:{original.task_id}")) > 0)

    # FINDING, not a bug fix (same category as the dispatched->completed
    # finding above): handoff()'s own guard is "if original.status not in
    # TERMINAL_STATUSES: cancel it" — a conditional on whether to *cancel*
    # the original, not a gate on whether handoff is allowed at all. A
    # terminal original is left exactly as it is (still completed, still
    # queryable) and a new linked task is still created. This is a
    # legitimate, arguably desirable behavior for the "continue this
    # conversation on my desktop now that the phone's quick task finished"
    # case — handoff() doubles as "spawn a new task carrying this one's
    # context forward" regardless of why the original ended. Verified
    # here as real behavior, not silently assumed to reject.
    router.ack(b_to_c.task_id, "hop-c")
    router.complete(b_to_c.task_id, "hop-c", result={})
    handoff_of_completed = router.handoff(b_to_c.task_id, "hop-a", reason="continue after completion")
    check("FINDING: handing off an already-completed task succeeds "
          "(creates a new linked task rather than rejecting)",
          handoff_of_completed.target_device_id == "hop-a")
    check("...the completed original is left completed, not reverted/touched",
          router.get(b_to_c.task_id).status == "completed")
    check("...and the new task still links back via handoff_of",
          handoff_of_completed.handoff_of == b_to_c.task_id)

    # Handoff to a nonexistent / incapable device is rejected
    live = router.create(origin="desktop", target_device_id="hop-a", action="open_app",
                          required_capability="app-launch")
    try:
        router.handoff(live.task_id, "no-such-device")
        check("handoff to an unknown device is rejected", False)
    except UnknownDeviceError:
        check("handoff to an unknown device is rejected", True)
    pair_device(registry, "hop-no-cam")  # paired, but reports zero capabilities
    try:
        router.handoff(live.task_id, "hop-no-cam", reason="wrong device")
        check("handoff to a device lacking the required capability is rejected", False)
    except CapabilityUnavailableError:
        check("handoff to a device lacking the required capability is rejected", True)


# ─── Event bus isolation & duplicate-event guarding (hardening pass) ─────

def test_event_bus_isolation():
    print("\n=== Event bus stream isolation (hardening pass) ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    caps = {"app-launch": {"available": True, "permission": "granted"}}
    pair_device(registry, "iso-a", capabilities=caps)
    pair_device(registry, "iso-b", capabilities=caps)

    events.publish_to(["device:iso-a", "device"], "device.connected", device_id="iso-a")
    events.publish_to(["device:iso-b", "device"], "device.connected", device_id="iso-b")
    a_events = events.get_since("device:iso-a")
    b_events = events.get_since("device:iso-b")
    check("device A's stream contains only A's event",
          len(a_events) == 1 and a_events[0]["device_id"] == "iso-a")
    check("device B's stream does not see A's event", all(e["device_id"] != "iso-a" for e in b_events))
    check("the shared 'device' stream sees both", len(events.get_since("device")) == 2)

    task_a = router.create(origin="desktop", target_device_id="iso-a", action="open_app",
                            required_capability="app-launch")
    task_b = router.create(origin="desktop", target_device_id="iso-b", action="open_app",
                            required_capability="app-launch")
    check("task A's stream does not contain task B's events",
          all(e.get("task_id") != task_b.task_id for e in events.get_since(f"task:{task_a.task_id}")))
    check("device A's stream contains task A's task.created (task+device cross-posting)",
          any(e["type"] == "task.created" for e in events.get_since("device:iso-a")))
    check("device B's stream does NOT contain task A's task.created",
          all(e.get("task_id") != task_a.task_id for e in events.get_since("device:iso-b")))

    # No duplicate events: publishing N times yields exactly N stored events
    before = len(events.get_since("voice"))
    events.publish("voice", "voice.started")
    events.publish("voice", "voice.stopped")
    after = len(events.get_since("voice"))
    check("publishing 2 distinct events adds exactly 2, not more", after - before == 2)


# ─── Offline/reconnect cycles (hardening pass) ───────────────────────────

def test_offline_reconnect_cycles():
    print("\n=== Repeated offline/reconnect cycles (hardening pass) ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    nonce_cache = lan_http.NonceCache()
    priv, _ = pair_device(registry, "cycle-1",
                           capabilities={"app-launch": {"available": True, "permission": "granted"}})

    task = router.create(origin="desktop", target_device_id="cycle-1", action="open_app",
                          required_capability="app-launch")
    check("task queued while device has never connected", task.status == "queued_offline")

    bring_online(registry, nonce_cache, priv, "cycle-1")
    pending_1 = router.get_pending_for_device("cycle-1")
    check("first heartbeat redelivers exactly one task", len(pending_1) == 1)

    # get_pending_for_device is a snapshot of "everything this device
    # still needs to handle" (status IN dispatched/queued_offline), not a
    # one-shot "newly redelivered" notification — see its own docstring.
    # So a second heartbeat before the device acks is EXPECTED to show
    # the same still-outstanding task again (safe/idempotent to poll), not
    # an empty list. Once acked, it correctly drops out of the set.
    pending_2 = router.get_pending_for_device("cycle-1")
    check("a second heartbeat (before ack) still reports the same outstanding task",
          len(pending_2) == 1 and pending_2[0].task_id == task.task_id)
    router.ack(task.task_id, "cycle-1")
    pending_after_ack = router.get_pending_for_device("cycle-1")
    check("once acked (-> started), the task drops out of the pending set",
          len(pending_after_ack) == 0)

    registry.sweep_offline(stale_after_seconds=-1)
    check("device reads offline after a forced sweep", 
          registry.get_device_by_external_id("cycle-1", channel=DIRECT_CHANNEL)["connection_state"] == "offline")

    task2 = router.create(origin="desktop", target_device_id="cycle-1", action="open_app",
                           required_capability="app-launch")
    check("a new task queues while offline again", task2.status == "queued_offline")

    bring_online(registry, nonce_cache, priv, "cycle-1")
    pending_3 = router.get_pending_for_device("cycle-1")
    check("reconnecting a second time redelivers only the new task (the first was acked, not re-shown)",
          len(pending_3) == 1 and pending_3[0].task_id == task2.task_id)

    registry.sweep_offline(stale_after_seconds=-1)
    bring_online(registry, nonce_cache, priv, "cycle-1")
    check("device is back online after a third cycle",
          registry.get_device_by_external_id("cycle-1", channel=DIRECT_CHANNEL)["connection_state"] == "online")


# ─── Concurrency (hardening pass, "if practical" per this pass's brief) ──

def test_concurrency():
    print("\n=== Concurrent access (hardening pass) ===")
    registry = DeviceRegistry()
    token = registry.create_pairing_token(channel=DIRECT_CHANNEL)

    # 10 threads racing to redeem the SAME one-time token, released
    # together via a Barrier to actually maximize contention rather than
    # just running sequentially with a shared GIL illusion of concurrency.
    redeem_results = []
    barrier = threading.Barrier(10)

    def try_redeem(i):
        barrier.wait()
        redeem_results.append(registry.redeem_token(token, f"concurrent-dev-{i}", channel=DIRECT_CHANNEL))

    threads = [threading.Thread(target=try_redeem, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    check("exactly one of 10 concurrent redemptions of the same token succeeds",
          sum(1 for r in redeem_results if r) == 1)
    race_rows = [d for d in registry.list_devices(include_pending=True)
                 if d["external_id"].startswith("concurrent-dev-")]
    check("exactly one device row exists from this race (no duplicate/corrupt rows)",
          len(race_rows) == 1)

    # 10 threads racing to create() with the SAME idempotency_key
    priv, pub = crypto.generate_keypair()
    lan_http.redeem_pairing(registry, {
        "token": registry.create_pairing_token(channel=DIRECT_CHANNEL), "device_id": "idem-race-dev",
        "device_name": "D", "platform": "android", "public_key": crypto.serialize_public_key(pub),
        "capabilities": {"app-launch": {"available": True, "permission": "granted"}},
    })
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    task_ids = []
    barrier2 = threading.Barrier(10)

    def try_create(i):
        barrier2.wait()
        t = router.create(origin="desktop", target_device_id="idem-race-dev", action="open_app",
                           required_capability="app-launch", idempotency_key="race-key-1")
        task_ids.append(t.task_id)

    threads2 = [threading.Thread(target=try_create, args=(i,)) for i in range(10)]
    for t in threads2:
        t.start()
    for t in threads2:
        t.join()
    check("10 concurrent create() calls with the same idempotency_key all return one task_id",
          len(set(task_ids)) == 1)


# ─── Nonce cache & replay window (hardening pass, audit of the nonce cache) ──

def test_nonce_cache_and_replay_window():
    print("\n=== Nonce cache & replay window (hardening pass) ===")

    # Plain NonceCache semantics
    cache = lan_http.NonceCache(ttl_seconds=60)
    check("a fresh (device, nonce) is accepted", cache.check_and_record("dev-1", "nonce-a") is True)
    check("the same (device, nonce) is rejected within its TTL",
          cache.check_and_record("dev-1", "nonce-a") is False)
    check("the same nonce under a different device_id is independent",
          cache.check_and_record("dev-2", "nonce-a") is True)
    check("a different nonce under the same device is independent",
          cache.check_and_record("dev-1", "nonce-b") is True)

    short = lan_http.NonceCache(ttl_seconds=0.05)
    short.check_and_record("dev-1", "n")
    time.sleep(0.1)
    check("an expired entry is treated as fresh (the timestamp window, not the cache, bounds replay age)",
          short.check_and_record("dev-1", "n") is True)

    # Bounded growth — white-box on _seen so the size threshold is hit
    # deterministically instead of racing a wall-clock TTL.
    churn = lan_http.NonceCache()
    churn._seen = {("d", f"n{i}"): 0.0 for i in range(5000)}  # 5000 already-expired entries
    churn.check_and_record("d", "fresh")
    check("expired entries are dropped once the cache passes its 4096-entry threshold",
          len(churn._seen) == 1)

    # Default TTL must cover the *full* replayable lifetime of a request, i.e. 2x the timestamp window
    check("default TTL is 2x TIMESTAMP_WINDOW_SECONDS",
          lan_http.NonceCache()._ttl == 2 * lan_http.TIMESTAMP_WINDOW_SECONDS)

    # Real replay gap (found by this test failing against the original 1x TTL): a device whose clock
    # runs ahead signs a request with ts = now + 100. It is accepted at t0, and its timestamp then stays
    # acceptable until ts + W = t0 + 220 — but a 1x (120s) cache forgets the nonce at t0 + 120.
    registry = DeviceRegistry()
    priv, _ = pair_device(registry, "skew-dev")
    nonce_cache = lan_http.NonceCache()  # default TTL: this is what is being tested
    real_now = time.time()
    ts = f"{real_now + 100:.6f}"
    nonce = secrets.token_urlsafe(16)
    method, path, body = "POST", "/api/connect/devices/skew-dev/heartbeat", b""
    sig = base64.b64encode(
        crypto.sign(priv, lan_http.canonical_message(method, path, ts, nonce, body))).decode()

    def verify():
        return lan_http.verify_request(registry, nonce_cache, method=method, path=path, body=body,
                                        device_id="skew-dev", timestamp=ts, nonce=nonce, signature_b64=sig)

    first = verify()
    check("a request from a device whose clock is 100s ahead is accepted once",
          first["external_id"] == "skew-dev")
    with mock.patch.object(lan_http.time, "time", return_value=real_now + 130):
        try:
            verify()
            check("replaying that request 130s later is rejected (nonce outlives the timestamp window it covers)",
                  False)
        except lan_http.ReplayedRequestError:
            check("replaying that request 130s later is rejected (nonce outlives the timestamp window it covers)",
                  True)
    with mock.patch.object(lan_http.time, "time", return_value=real_now + 100 + lan_http.TIMESTAMP_WINDOW_SECONDS + 5):
        try:
            verify()
            check("...and once the timestamp itself is out of window, it is rejected on that ground", False)
        except lan_http.TimestampOutOfRangeError:
            check("...and once the timestamp itself is out of window, it is rejected on that ground", True)


def test_failed_auth_does_not_touch_nonce_cache():
    print("\n=== Unauthenticated input must not mutate replay state (hardening pass) ===")
    registry = DeviceRegistry()
    nonce_cache = lan_http.NonceCache()
    priv, _ = pair_device(registry, "burn-dev")
    path = "/api/connect/devices/burn-dev/heartbeat"
    garbage_sig = base64.b64encode(b"x" * 64).decode()

    for _ in range(50):
        try:
            lan_http.verify_request(registry, nonce_cache, method="POST", path=path, body=b"",
                                     device_id="burn-dev", timestamp=str(time.time()),
                                     nonce=secrets.token_urlsafe(16), signature_b64=garbage_sig)
        except lan_http.DeviceAuthError:
            pass
    check("50 requests that fail signature verification record nothing in the nonce cache",
          len(nonce_cache._seen) == 0)

    for i in range(50):
        try:
            lan_http.verify_request(registry, nonce_cache, method="POST", path=path, body=b"",
                                     device_id=f"ghost-{i}", timestamp=str(time.time()),
                                     nonce=secrets.token_urlsafe(16), signature_b64=garbage_sig)
        except lan_http.DeviceAuthError:
            pass
    check("50 requests from never-paired device_ids record nothing either", len(nonce_cache._seen) == 0)

    # A forged request reusing a legitimate request's nonce must not burn it: an attacker who can see the
    # request in flight and inject a tampered copy first must not make the legitimate one a "replay".
    ts = str(time.time())
    nonce = secrets.token_urlsafe(16)
    legit_sig = base64.b64encode(
        crypto.sign(priv, lan_http.canonical_message("POST", path, ts, nonce, b""))).decode()
    try:
        lan_http.verify_request(registry, nonce_cache, method="POST", path=path, body=b"tampered",
                                 device_id="burn-dev", timestamp=ts, nonce=nonce, signature_b64=legit_sig)
        check("the forged copy is rejected", False)
    except lan_http.InvalidSignatureError:
        check("the forged copy is rejected", True)
    try:
        lan_http.verify_request(registry, nonce_cache, method="POST", path=path, body=b"",
                                 device_id="burn-dev", timestamp=ts, nonce=nonce, signature_b64=legit_sig)
        check("the legitimate request with the same nonce still succeeds afterwards", True)
    except lan_http.DeviceAuthError as e:
        check(f"the legitimate request with the same nonce still succeeds afterwards (got {type(e).__name__})", False)
    check("and only the successful request was recorded", len(nonce_cache._seen) == 1)


# ─── Private key never reaches the server (hardening pass) ───────────────

def test_server_never_stores_private_key():
    print("\n=== Private key never crosses the wire or lands in the DB (hardening pass) ===")
    registry = DeviceRegistry()
    priv, pub = crypto.generate_keypair()
    priv_pem = crypto.serialize_private_key(priv)
    pub_pem = crypto.serialize_public_key(pub)
    token = lan_http.build_pairing_qr_payload(registry, port=8420)["token"]

    try:
        lan_http.redeem_pairing(registry, {
            "token": token, "device_id": "pk-dev", "device_name": "x", "platform": "android",
            "public_key": priv_pem, "capabilities": {},
        })
        check("a private key PEM submitted as public_key is rejected", False)
    except ValueError:
        check("a private key PEM submitted as public_key is rejected", True)
    check("the rejected submission created no trusted device", not registry.is_trusted("pk-dev", channel=DIRECT_CHANNEL))

    try:
        lan_http.redeem_pairing(registry, {
            "token": token, "device_id": "pk-dev", "device_name": "x", "platform": "android",
            "public_key": "definitely not a key", "capabilities": {},
        })
        check("a garbage public_key is rejected", False)
    except ValueError:
        check("a garbage public_key is rejected", True)

    result = lan_http.redeem_pairing(registry, {
        "token": token, "device_id": "pk-dev", "device_name": "x", "platform": "android",
        "public_key": pub_pem, "capabilities": {},
    })
    check("a valid public key still pairs successfully with the same token afterwards "
          "(malformed submissions are validated before the token is consumed)",
          result["status"] == "trusted")

    with open(registry.db_path(), "rb") as f:
        raw = f.read()
    check("the registry's SQLite file contains no PRIVATE KEY PEM marker", b"PRIVATE KEY" not in raw)
    check("...and does contain the device's public key", b"BEGIN PUBLIC KEY" in raw)


# ─── Every documented event type (hardening pass) ────────────────────────

def test_all_event_types():
    print("\n=== Every documented event type publishes and routes (hardening pass) ===")
    from connect.core.events import ALL_EVENT_TYPES, TERMINAL_TASK_EVENT_TYPES
    events = ConnectEventBus()
    check("the documented vocabulary has exactly 13 event types", len(ALL_EVENT_TYPES) == 13)
    for etype in sorted(ALL_EVENT_TYPES):
        stream = f"probe:{etype}"  # one stream per type so the terminal guard cannot interfere
        ev = events.publish(stream, etype, marker=etype)
        got = events.get_since(stream)
        check(f"{etype} publishes and reads back with its own type",
              ev is not None and len(got) == 1 and got[0]["type"] == etype)
    check("exactly task.completed/task.failed/task.cancelled are terminal",
          TERMINAL_TASK_EVENT_TYPES == {"task.completed", "task.failed", "task.cancelled"})
    for etype in sorted(TERMINAL_TASK_EVENT_TYPES):
        stream = f"task:term-{etype}"
        events.publish(stream, "task.created")
        events.publish(stream, etype)
        late = events.publish(stream, "task.progress")
        check(f"after {etype}, further events on that task stream are ignored", late is None)


def main():
    test_pairing_and_trust()
    test_revocation_and_repairing()
    test_signature_verification()
    test_capabilities()
    test_task_lifecycle()
    test_idempotency()
    test_offline_queueing_and_redelivery()
    test_timeout_sweep()
    test_handoff()
    test_sweep_offline()
    test_event_bus()
    test_crypto_adversarial()
    test_pairing_security_extra()
    test_state_machine_transitions()
    test_handoff_multi_hop()
    test_event_bus_isolation()
    test_offline_reconnect_cycles()
    test_concurrency()
    test_nonce_cache_and_replay_window()
    test_failed_auth_does_not_touch_nonce_cache()
    test_server_never_stores_private_key()
    test_all_event_types()

    print(f"\n{'=' * 60}")
    passed = sum(1 for r in results if r)
    print(f"{passed}/{len(results)} checks passed")
    print(
        "\nNOTE: this suite exercises connect/core, connect/transports and\n"
        "connect/services directly — real logic, real SQLite, real Ed25519\n"
        "signatures, no mocks. It does NOT exercise the FastAPI layer\n"
        "(interfaces/api/device_auth.py, connect_routes.py, connect_schemas.py)\n"
        "since fastapi/pydantic/uvicorn were not available in the sandbox this\n"
        "suite was written in — see tests/test_connect_api_offline.py for that\n"
        "coverage, and run it in the real dev environment before merging.\n"
        "No real Android device or real Mac was available either; 'online'\n"
        "devices in this suite are the offline test suite's own signed\n"
        "requests, not a physical phone. See docs/architecture/\n"
        "CROSS_DEVICE_PROTOCOL.md for the real-device validation this still\n"
        "needs."
    )
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
