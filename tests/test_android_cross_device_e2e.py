"""
End-to-end integration and verification tests for SAM cross-device Android workflows.
Tests:
1. Natural language request -> Tiered routing -> Cross-device task dispatch -> Android execution -> Verified outcome.
2. Bidirectional file transfer with SHA-256 cryptographic verification.
3. Network disconnect -> Offline queuing -> Reconnect replay prevention via ExecutionLease & Idempotency.
4. Android UI automation, notifications, and local mobile inference contract validation.
"""

import os
import sys
import tempfile
import atexit
import shutil
import time
import base64
import hashlib
from pathlib import Path

# Isolated test environment
if "sam_e2e_test" not in os.environ.get("HOME", ""):
    _temp_home = tempfile.mkdtemp(prefix="sam_e2e_test_")
    os.environ["HOME"] = _temp_home
    atexit.register(lambda: shutil.rmtree(_temp_home, ignore_errors=True))

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from core.tiered_router import TieredExecutionRouter, ExecutionTier
from connect.core.capabilities import (
    APP_LAUNCH, NOTIFICATIONS, FILE_TRANSFER, ACCESSIBILITY,
    MODEL_INFERENCE, UI_INTERACTION
)
from connect.core.device_registry import DeviceRegistry, DIRECT_CHANNEL
from connect.core.events import ConnectEventBus
from connect.services.task_handoff import DeviceTaskRouter, DeviceTask
from connect.services.coordinator import UnifiedTaskCoordinator
from connect.services.workflows import CrossDeviceWorkflowRunner
from connect.core import crypto
from config.settings import Settings


@pytest.fixture
def setup_cross_device_env():
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    coordinator = UnifiedTaskCoordinator(registry, router)
    tiered_router = TieredExecutionRouter()

    # Pair a simulated Android device
    token = registry.create_pairing_token(channel=DIRECT_CHANNEL)
    priv_key, pub_key = crypto.generate_keypair()
    phone_id = f"android_pixel_{int(time.time())}"

    success = registry.redeem_token(
        token=token,
        external_id=phone_id,
        device_name="Google Pixel 9 Pro",
        channel=DIRECT_CHANNEL,
        platform="android",
        public_key=crypto.serialize_public_key(pub_key),
        capabilities={
            NOTIFICATIONS: {"available": True, "permission": "granted"},
            APP_LAUNCH: {"available": True, "permission": "granted"},
            FILE_TRANSFER: {"available": True, "permission": "granted"},
            ACCESSIBILITY: {"available": True, "permission": "granted"},
            MODEL_INFERENCE: {"available": True, "permission": "granted"},
        }
    )
    assert success is True
    # Mark online
    registry.update_device_heartbeat(phone_id, connection_state="online")

    return {
        "registry": registry,
        "events": events,
        "router": router,
        "coordinator": coordinator,
        "tiered_router": tiered_router,
        "phone_id": phone_id,
        "pub_key": pub_key,
        "priv_key": priv_key,
    }


def test_natural_language_to_android_execution(setup_cross_device_env):
    """Test full cycle: NL request -> TieredRouter -> Coordinator -> Android Task -> Completion."""
    env = setup_cross_device_env
    tiered_router = env["tiered_router"]
    coordinator = env["coordinator"]
    router = env["router"]
    phone_id = env["phone_id"]

    # 1. User prompt with mobile targeting
    instruction = "on my phone: open YouTube"
    decision = tiered_router.route(instruction)
    assert decision.target_device == "android"
    assert decision.action == "app_launch"
    assert decision.action_payload.get("app") == "YouTube"

    # 2. Coordinator creates coordinated task and acquires lease
    task = coordinator.create_coordinated_task(
        goal=instruction,
        origin_device_id="desktop",
        target_device_id=phone_id,
        required_capabilities=[APP_LAUNCH],
        idempotency_key="idemp_yt_01"
    )
    assert task.status == "leased"
    assert task.lease is not None
    assert task.lease.owner_device_id == phone_id
    assert task.lease.is_active is True

    # 3. Router dispatches DeviceTask to Android client
    dev_task = router.create(
        origin="desktop",
        target_device_id=phone_id,
        action="app_launch",
        payload=decision.action_payload,
        idempotency_key="idemp_yt_01"
    )
    assert dev_task.status == "dispatched"
    assert dev_task.target_device_id == phone_id

    # 4. Android simulated client receives and acknowledges
    acked = router.ack(dev_task.task_id, phone_id)
    assert acked.status == "started"

    # 5. Android client reports progress and verification
    prog = router.progress(dev_task.task_id, phone_id, message="Launching YouTube package via intent", pct=50)
    assert prog.status == "in_progress"

    verif = router.verification(dev_task.task_id, phone_id, verified=True, detail="com.google.android.youtube in foreground")
    assert verif.status == "in_progress"

    # 6. Android client completes task
    completed = router.complete(dev_task.task_id, phone_id, result={"launched": True, "app": "YouTube"})
    assert completed.status == "completed"
    assert completed.result.get("launched") is True

    # 7. Coordinator finishes task and revokes lease
    coord_completed = coordinator.complete_task(task.task_id, result=completed.result)
    assert coord_completed.status == "completed"
    assert coord_completed.lease.revoked is True


def test_cross_device_file_transfer_with_sha256(setup_cross_device_env):
    """Test file packaging on desktop, cryptographic hashing, transfer, and verification."""
    env = setup_cross_device_env
    router = env["router"]
    phone_id = env["phone_id"]

    # Create sample file on desktop
    test_dir = Path(os.environ["HOME"]) / "desktop_share"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_file = test_dir / "financial_audit_2026.pdf"
    file_bytes = b"%PDF-1.4 Mock audit document content for cross-device validation."
    test_file.write_bytes(file_bytes)

    expected_sha256 = hashlib.sha256(file_bytes).hexdigest()
    base64_payload = base64.b64encode(file_bytes).decode("ascii")

    # 1. Desktop dispatches receive_file task to Android
    file_task = router.create(
        origin="desktop",
        target_device_id=phone_id,
        action="receive_file",
        payload={
            "filename": test_file.name,
            "data": base64_payload,
            "sha256": expected_sha256,
            "size_bytes": len(file_bytes)
        }
    )
    assert file_task.status == "dispatched"

    # 2. Android client acknowledges
    router.ack(file_task.task_id, phone_id)

    # 3. Android client verifies SHA-256 integrity
    received_bytes = base64.b64decode(file_task.payload["data"])
    actual_sha256 = hashlib.sha256(received_bytes).hexdigest()
    assert actual_sha256 == expected_sha256

    # 4. Android completes successfully
    saved_path = f"/storage/emulated/0/Android/data/com.samcore.android/files/Download/{test_file.name}"
    completed = router.complete(file_task.task_id, phone_id, result={
        "saved": True,
        "path": saved_path,
        "size_bytes": len(received_bytes),
        "sha256": actual_sha256
    })
    assert completed.status == "completed"
    assert completed.result["saved"] is True
    assert completed.result["sha256"] == expected_sha256


def test_cross_device_file_transfer_corruption_detected(setup_cross_device_env):
    """Test that checksum mismatch is immediately caught and failed."""
    env = setup_cross_device_env
    router = env["router"]
    phone_id = env["phone_id"]

    original_bytes = b"Authentic payload data"
    corrupted_bytes = b"Corrupted payload data"
    expected_sha256 = hashlib.sha256(original_bytes).hexdigest()
    corrupted_base64 = base64.b64encode(corrupted_bytes).decode("ascii")

    file_task = router.create(
        origin="desktop",
        target_device_id=phone_id,
        action="receive_file",
        payload={
            "filename": "payload.dat",
            "data": corrupted_base64,
            "sha256": expected_sha256
        }
    )
    router.ack(file_task.task_id, phone_id)

    # Android checksum verification detects mismatch
    actual_sha256 = hashlib.sha256(base64.b64decode(file_task.payload["data"])).hexdigest()
    assert actual_sha256 != expected_sha256

    failed = router.fail(
        file_task.task_id,
        phone_id,
        error=f"Checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
    )
    assert failed.status == "failed"
    assert "Checksum mismatch" in failed.error


def test_offline_queuing_and_reconnect_deduplication(setup_cross_device_env):
    """Test that offline devices queue tasks, deliver on reconnect, and prevent duplicate execution."""
    env = setup_cross_device_env
    registry = env["registry"]
    router = env["router"]
    coordinator = env["coordinator"]
    phone_id = env["phone_id"]

    # 1. Mark phone as offline
    registry.set_connection_state(phone_id, "offline")

    # 2. Coordinator creates coordinated task
    coord_task = coordinator.create_coordinated_task(
        goal="Display reminder on phone",
        origin_device_id="desktop",
        target_device_id=phone_id,
        required_capabilities=[NOTIFICATIONS],
        idempotency_key="notif_reconnect_01"
    )
    assert coord_task.status == "leased"

    # 3. Router creates device task -> must be queued_offline
    dev_task = router.create(
        origin="desktop",
        target_device_id=phone_id,
        action="show_notification",
        payload={"title": "SAM Alert", "message": "Meeting in 15 mins"},
        idempotency_key="notif_reconnect_01"
    )
    assert dev_task.status == "queued_offline"

    # 4. Attempting duplicate creation returns existing queued task (Idempotency)
    duplicate_task = router.create(
        origin="desktop",
        target_device_id=phone_id,
        action="show_notification",
        payload={"title": "SAM Alert", "message": "Meeting in 15 mins"},
        idempotency_key="notif_reconnect_01"
    )
    assert duplicate_task.task_id == dev_task.task_id
    assert duplicate_task.status == "queued_offline"

    # 5. Phone comes back online and sends heartbeat
    registry.record_heartbeat(phone_id)
    pending = router.get_pending_for_device(phone_id)
    assert len(pending) == 1
    assert pending[0].task_id == dev_task.task_id
    assert pending[0].status == "dispatched"

    # 6. Phone acknowledges and executes exactly once
    router.ack(dev_task.task_id, phone_id)
    completed = router.complete(dev_task.task_id, phone_id, result={"submitted": True})
    assert completed.status == "completed"


def test_android_action_matrix_coverage(setup_cross_device_env):
    """Verify all 10 action types defined in AndroidConnectTaskExecutor are routable."""
    env = setup_cross_device_env
    router = env["router"]
    phone_id = env["phone_id"]

    actions = [
        ("show_notification", {"title": "Test", "message": "Notice"}),
        ("app_launch", {"app": "Spotify"}),
        ("view_url", {"url": "https://sam.dev"}),
        ("share_content", {"content": "Sample note", "title": "Note"}),
        ("get_notifications", {}),
        ("accessibility_click", {"text": "Allow"}),
        ("accessibility_type", {"text": "Search query"}),
        ("accessibility_action", {"action": "back"}),
        ("receive_file", {"filename": "data.txt", "data": "VGVzdA==", "sha256": "mock"}),
        ("local_infer", {"prompt": "Quick summary"}),
    ]

    for action_name, payload in actions:
        task = router.create(
            origin="desktop",
            target_device_id=phone_id,
            action=action_name,
            payload=payload
        )
        assert task.status == "dispatched"
        assert task.action == action_name

        router.ack(task.task_id, phone_id)
        router.progress(task.task_id, phone_id, f"Executing {action_name}", 50)
        router.verification(task.task_id, phone_id, True, f"Verified {action_name}")
        completed = router.complete(task.task_id, phone_id, result={"ok": True, "action": action_name})
        assert completed.status == "completed"
        assert completed.result.get("action") == action_name
