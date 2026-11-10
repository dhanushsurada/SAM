"""
Comprehensive Offline Test Suite for Tiered Execution, Cross-Device Coordinator,
Security Approval Policy, and Performance Telemetry.
"""

import os
import sys
import tempfile
import atexit
import shutil
import time
from pathlib import Path

# Isolated test environment
if "sam_tiered_test" not in os.environ.get("HOME", ""):
    _temp_home = tempfile.mkdtemp(prefix="sam_tiered_test_")
    os.environ["HOME"] = _temp_home
    atexit.register(lambda: shutil.rmtree(_temp_home, ignore_errors=True))

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.tiered_router import TieredExecutionRouter, ExecutionTier
from core.instrumentation import PerformanceProfiler, TurnMetrics
from connect.core.capabilities import (
    APP_LAUNCH, NOTIFICATIONS, FILE_TRANSFER, BROWSER, TERMINAL, DOCUMENTS,
    device_supports
)
from connect.core.device_registry import DeviceRegistry, DIRECT_CHANNEL
from connect.core.events import ConnectEventBus
from connect.services.task_handoff import DeviceTaskRouter
from connect.services.coordinator import UnifiedTaskCoordinator
from connect.services.workflows import CrossDeviceWorkflowRunner
from connect.core.security_policy import SecurityPolicyEngine, RiskLevel
from config.settings import Settings

results = []

def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(bool(condition))
    print(f"[{status}] {label}")


def test_tiered_router():
    print("\n=== Tiered Execution Router ===")
    router = TieredExecutionRouter()

    # 1. Math calculation -> Tier 1
    d1 = router.route("calculate 45 * 2")
    check("Math expression routed to Tier 1 Direct", d1.tier == ExecutionTier.DIRECT)
    check("Math action is calculate", d1.action == "calculate")
    check("Math expression is parsed", d1.action_payload.get("expression") == "45 * 2")

    # 2. App Launch -> Tier 1
    d2 = router.route("open Chrome")
    check("Open app routed to Tier 1 Direct", d2.tier == ExecutionTier.DIRECT)
    check("Resolved app name is Google Chrome", d2.action_payload.get("app") == "Google Chrome")
    check("Desktop target assigned", d2.target_device == "desktop")

    # 3. Mobile targeting
    d3 = router.route("on my phone: open WhatsApp")
    check("Mobile prefix routes to Android target", d3.target_device == "android")
    check("Mobile app action is app_launch", d3.action == "app_launch")

    # 4. Screenshot -> Tier 1
    d4 = router.route("take a screenshot")
    check("Screenshot routed to Tier 1 Direct", d4.tier == ExecutionTier.DIRECT)
    check("Screenshot payload type is screenshot", d4.action_payload.get("type") == "screenshot")

    # 5. Multi-step conjunctions -> Tier 3
    d5 = router.route("open browser and then search for flight tickets after that book one")
    check("Multi-step task routed to Tier 3 Advanced", d5.tier == ExecutionTier.ADVANCED)
    check("Requires planning is True", d5.requires_planning is True)


def test_unified_coordinator():
    print("\n=== Unified Task Coordinator & Leased Ownership ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    coordinator = UnifiedTaskCoordinator(registry, router)

    # 1. Desktop capability check
    caps = coordinator.get_desktop_capabilities()
    check("Desktop has browser capability", caps[BROWSER]["available"] is True)
    check("Desktop has terminal capability", caps[TERMINAL]["available"] is True)

    # 2. Task creation with execution lease
    task = coordinator.create_coordinated_task(
        goal="Analyse report and generate document",
        origin_device_id="desktop",
        target_device_id="desktop",
        required_capabilities=[DOCUMENTS],
        idempotency_key="idemp_101"
    )
    check("Coordinated task created with task_id", bool(task.task_id))
    check("Task has an active lease", task.lease is not None and task.lease.is_active)
    check("Lease owner matches target device", task.lease.owner_device_id == "desktop")

    # 3. Idempotency test
    dup_task = coordinator.create_coordinated_task(
        goal="Analyse report and generate document",
        origin_device_id="desktop",
        target_device_id="desktop",
        required_capabilities=[DOCUMENTS],
        idempotency_key="idemp_101"
    )
    check("Duplicate creation returns identical task", dup_task.task_id == task.task_id)

    # 4. Task Handoff
    transferred = coordinator.transfer_task(
        task_id=task.task_id,
        to_device_id="mobile_device_alpha",
        step_result="Analysis complete",
        next_goal="Display summary on mobile"
    )
    check("Task current device updated to mobile", transferred.current_device_id == "mobile_device_alpha")
    check("Status updated to transferring", transferred.status == "transferring")
    check("New lease granted to mobile device", transferred.lease.owner_device_id == "mobile_device_alpha")
    check("Handoff history contains desktop", "desktop" in transferred.handoff_history)

    # 5. Completion
    completed = coordinator.complete_task(task.task_id, result="Success report")
    check("Task status completed", completed.status == "completed")
    check("Lease revoked on completion", completed.lease.revoked is True)


def test_cross_device_workflows():
    print("\n=== Cross-Device Workflows Engine ===")
    registry = DeviceRegistry()
    events = ConnectEventBus()
    router = DeviceTaskRouter(registry, events)
    coordinator = UnifiedTaskCoordinator(registry, router)
    settings = Settings()
    workflow_runner = CrossDeviceWorkflowRunner(coordinator, router, settings)

    # Setup dummy paired device for test
    token = registry.create_pairing_token(channel=DIRECT_CHANNEL)
    from connect.core import crypto
    import secrets
    priv, pub = crypto.generate_keypair()
    phone_id = f"phone_{secrets.token_hex(8)}"
    redeem_ok = registry.redeem_token(
        token=token,
        external_id=phone_id,
        device_name="Test Phone",
        channel=DIRECT_CHANNEL,
        platform="android",
        public_key=crypto.serialize_public_key(pub),
        capabilities={
            NOTIFICATIONS: {"available": True, "permission": "granted"},
            FILE_TRANSFER: {"available": True, "permission": "granted"},
            APP_LAUNCH: {"available": True, "permission": "granted"}
        }
    )
    assert redeem_ok is True

    # 1. File transfer workflow
    test_file_dir = Path(os.environ["HOME"]) / "test_docs"
    test_file_dir.mkdir(parents=True, exist_ok=True)
    sample_pdf = test_file_dir / "invoice_q3.pdf"
    sample_pdf.write_bytes(b"%PDF-1.4 sample pdf content for cross-device transfer")

    res = workflow_runner.execute_file_transfer_to_mobile(
        query="invoice_q3",
        search_dir=test_file_dir,
        target_device_id=phone_id
    )
    check("File transfer workflow dispatched", res.get("success") is True)
    check("Filename correctly discovered", res.get("filename") == "invoice_q3.pdf")
    check("SHA256 checksum generated", bool(res.get("sha256")))

    # 2. Notification summary workflow
    notif_res = workflow_runner.execute_mobile_notifications_to_desktop_report(
        mobile_device_id=phone_id,
        report_title="Daily Mobile Briefing"
    )
    check("Notification collection initiated", notif_res.get("success") is True)
    check("Coordinated task created for notifications", bool(notif_res.get("task_id")))

    # Complete on desktop with sample notifications
    sample_notifications = [
        {"app": "Slack", "title": "Team Alpha", "text": "Deploy succeeded on staging."},
        {"app": "Gmail", "title": "GitHub", "text": "Pull request #42 approved."}
    ]
    report_res = workflow_runner.complete_notification_report_on_desktop(
        coordinated_task_id=notif_res["task_id"],
        notifications=sample_notifications,
        report_title="Daily Mobile Briefing"
    )
    check("Report document generated on desktop", report_res.get("success") is True)
    check("Document creation reported", "Created" in report_res.get("document_result", ""))


def test_performance_profiler():
    print("\n=== Performance Instrumentation & Metrics ===")
    profiler = PerformanceProfiler()
    turn = profiler.start_turn("task_perf_1", "calculate 10 + 20")
    turn.metrics.tier = "tier_1_direct"
    time.sleep(0.005)
    turn.record_first_token()
    turn.record_tool_call("calculate", elapsed_ms=1.2, success=True)
    metrics = turn.finish(success=True)

    check("Total latency recorded", metrics.total_latency_ms > 0)
    check("TTFT recorded", metrics.time_to_first_token_ms > 0)
    check("Tool breakdown recorded", len(metrics.tool_breakdown) == 1)
    check("Zero model calls for direct tier", metrics.model_call_count == 0)

    summary = profiler.get_summary()
    check("Profiler summary includes total_tasks", summary["total_tasks"] == 1)
    check("Success rate is 100%", summary["success_rate"] == 1.0)


def test_security_policy():
    print("\n=== Security Approval Policy & Risk Levels ===")
    policy = SecurityPolicyEngine()

    check("Calculate is LOW risk", policy.classify_action("calculate") == RiskLevel.LOW)
    check("Open app is MEDIUM risk", policy.classify_action("app_launch") == RiskLevel.MEDIUM)
    check("Delete file is HIGH risk", policy.classify_action("delete_file") == RiskLevel.HIGH)
    check("Dangerous terminal command is HIGH risk", policy.classify_action("terminal", {"command": "rm -rf /"}) == RiskLevel.HIGH)

    needs_app, risk, reason = policy.requires_approval("delete_file")
    check("High risk requires approval", needs_app is True)

    needs_app_safe, _, _ = policy.requires_approval("calculate")
    check("Low risk executes without approval", needs_app_safe is False)


if __name__ == "__main__":
    test_tiered_router()
    test_unified_coordinator()
    test_cross_device_workflows()
    test_performance_profiler()
    test_security_policy()

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n============================================================")
    print(f"{passed}/{total} checks passed.")
    if passed == total:
        print("All Tiered Execution & Cross-Device tests PASSED!")
    else:
        sys.exit(1)
