"""
Offline smoke test for iQOO Phase 1 (phone task gateway) — no live
Ollama, no phone, no network required. Brain/ReactLoop/Memory/Identity/
FounderMode are mocked exactly like test_phase2_telegram_offline.py mocks
Telegram's Update/Context — this tests the gateway's own logic (task
lifecycle, cancellation, concurrency serialization, API wiring), not the
Brain's actual reasoning quality (that needs the real Mac + Ollama, per
the PDR's "manually test" requirement).

Usage:
    HOME=/tmp/sam_iqoo_test python3 tests/test_iqoo_phase1_offline.py
"""

import sys
import time
import json
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


@dataclass
class FakeBrainResponse:
    text: str
    action: str = None
    action_payload: dict = None


def make_mocked_gateway():
    """Builds a TaskGateway with every SAM-core dependency mocked, the
    same pattern test_phase2_telegram_offline.py uses for Telegram's
    Update/Context. Patches the source classes (not iqoo.gateway's local
    imports) since gateway.py imports them lazily inside __init__."""
    with patch("memory.identity.Identity") as MockIdentity, \
         patch("memory.retrieve.MemoryRetriever") as MockMemory, \
         patch("founder_mode.manager.FounderModeManager") as MockFounder, \
         patch("core.brain.Brain") as MockBrain, \
         patch("agent.react_loop.ReactLoop") as MockReactLoop:

        MockIdentity.return_value.load.return_value = {}
        MockMemory.return_value.retrieve.return_value = []
        MockMemory.return_value.get_store.return_value = None
        MockFounder.return_value.get_context.return_value = ""
        MockFounder.return_value.capture_if_relevant.return_value = None
        MockBrain.return_value._check_ollama.return_value = True

        from config.settings import Settings
        settings = Settings()
        settings.incognito = True  # skip session.save() entirely in tests

        from iqoo.gateway import TaskGateway
        gateway = TaskGateway(settings=settings)
        return gateway, MockBrain.return_value, MockReactLoop.return_value


def wait_for_status(gateway, task_id, statuses, timeout=5.0):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        record = gateway.get_task(task_id)
        last = record["status"] if record else None
        if last in statuses:
            return last
        time.sleep(0.05)
    return last


def test_task_store():
    from iqoo.task_store import TaskStore, TERMINAL_STATUSES

    store = TaskStore()
    task_id = store.create_task("Open Safari", "text", [])
    record = store.get_task(task_id)
    check("Task created with queued status", record["status"] == "queued")
    check("Task instruction stored correctly", record["instruction"] == "Open Safari")
    check("Unknown task returns None", store.get_task("does-not-exist") is None)

    store.update_status(task_id, "executing")
    check("Status update persisted", store.get_task(task_id)["status"] == "executing")

    ok = store.request_cancel(task_id)
    check("Cancel request accepted for running task", ok is True)
    check("Cancel event actually set", store.get_cancel_event(task_id).is_set())

    store.update_status(task_id, "completed", result_text="Done")
    ok2 = store.request_cancel(task_id)
    check("Cancel rejected after task already terminal", ok2 is False)
    check("Terminal statuses set is correct", TERMINAL_STATUSES == {"completed", "failed", "cancelled"})


def test_event_bus():
    from iqoo.events import EventBus

    bus = EventBus()
    bus.publish("t1", "planning", "Plan created")
    bus.publish("t1", "executing", "Step 1")
    q = bus.subscribe_queue("t1")
    e1 = q.get(timeout=1)
    e2 = q.get(timeout=1)
    check("First event has correct phase", e1["phase"] == "planning")
    check("Second event has correct phase", e2["phase"] == "executing")
    check("Event has task_id", e1["task_id"] == "t1")
    bus.cleanup("t1")
    check("Cleanup removes queue (new subscribe gives fresh queue)",
          bus.subscribe_queue("t1").empty())


def test_gateway_no_action_task():
    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    try:
        mock_brain.process.return_value = FakeBrainResponse(text="It's 3pm.", action=None)
        task_id = gateway.submit_task("what time is it")
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Conversational task completes without calling ReactLoop",
              final == "completed" and not mock_react_loop.run_planned_task.called)
        check("Result text captured", record["result_text"] == "It's 3pm.")
    finally:
        gateway.shutdown()


def test_gateway_action_task():
    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    try:
        mock_brain.process.return_value = FakeBrainResponse(
            text="Opening Safari...", action="control", action_payload={"type": "open_app", "app": "Safari"})
        mock_react_loop.run_planned_task.return_value = "Opened Safari."
        task_id = gateway.submit_task("open safari")
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Action task routes through ReactLoop.run_planned_task",
              mock_react_loop.run_planned_task.called)
        check("Action task completes with real executed result",
              final == "completed" and record["result_text"] == "Opened Safari.")
        # The gateway must invoke the SAME entry point main.py uses, not a
        # parallel execution path.
        _, kwargs = mock_react_loop.run_planned_task.call_args
        check("on_event callback passed through (progress streaming wired)",
              "on_event" in kwargs and callable(kwargs["on_event"]))
        check("cancel_event passed through (real interrupt, not UI-only)",
              "cancel_event" in kwargs)
    finally:
        gateway.shutdown()


def test_gateway_cancel_before_start():
    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    try:
        # Block the worker on a slow first task so our cancel target
        # stays queued long enough to cancel before it starts.
        block = MagicMock()
        slow_holder = {"go": False}

        def slow_process(session):
            while not slow_holder["go"]:
                time.sleep(0.01)
            return FakeBrainResponse(text="done", action=None)

        mock_brain.process.side_effect = slow_process
        blocker_id = gateway.submit_task("slow task")
        target_id = gateway.submit_task("cancel me")

        ok = gateway.cancel_task(target_id)
        check("Cancel accepted while task still queued", ok is True)

        slow_holder["go"] = True
        wait_for_status(gateway, blocker_id, {"completed", "failed"})
        final = wait_for_status(gateway, target_id, {"completed", "failed", "cancelled"})
        check("Queued task never executes after cancellation", final == "cancelled")
        check("Unknown task_id cancel returns False", gateway.cancel_task("nope") is False)
    finally:
        gateway.shutdown()


def test_gateway_execution_failure():
    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    try:
        mock_brain.process.side_effect = RuntimeError("ollama unreachable")
        task_id = gateway.submit_task("do something")
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Brain exception reported as failed, not silently dropped", final == "failed")
        check("Error message captured", "ollama unreachable" in (record["error"] or ""))
    finally:
        gateway.shutdown()


def test_gateway_retry():
    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    try:
        mock_brain.process.return_value = FakeBrainResponse(text="ok", action=None)
        task_id = gateway.submit_task("do X")
        wait_for_status(gateway, task_id, {"completed", "failed"})
        new_id = gateway.retry_task(task_id)
        check("Retry creates a NEW task_id, not reusing the old one", new_id != task_id)
        wait_for_status(gateway, new_id, {"completed", "failed"})
        check("Retried task also completes", gateway.get_task(new_id)["status"] == "completed")
        check("Retry of unknown task_id returns None", gateway.retry_task("nope") is None)
    finally:
        gateway.shutdown()


def test_gateway_unsupported_input_type():
    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    try:
        task_id = gateway.submit_task("turn this into a backend", input_type="image+voice",
                                       attachments=[{"kind": "image", "data": "..."}])
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Phase 1 fails multimodal tasks honestly instead of ignoring attachments",
              final == "failed" and "Phase 2" in (record["error"] or ""))
        check("Brain never called for unsupported input type in Phase 1",
              not mock_brain.process.called)
    finally:
        gateway.shutdown()


def test_api_endpoints():
    from fastapi.testclient import TestClient
    import iqoo.server as server_module

    gateway, mock_brain, mock_react_loop = make_mocked_gateway()
    mock_brain.process.return_value = FakeBrainResponse(text="hi there", action=None)
    server_module._gateway = gateway  # inject our mocked gateway instead of building a real one

    client = TestClient(server_module.app)

    r = client.get("/api/iqoo/health")
    check("Health endpoint returns 200", r.status_code == 200)
    check("Health reports brain_reachable", r.json()["brain_reachable"] is True)

    r = client.post("/api/iqoo/tasks", json={"instruction": "say hi"})
    check("Task creation returns 201", r.status_code == 201)
    task_id = r.json()["task_id"]

    r = client.post("/api/iqoo/tasks", json={"instruction": ""})
    check("Empty instruction rejected with 422", r.status_code == 422)

    r = client.post("/api/iqoo/tasks", json={"input_type": "text"})
    check("Missing instruction field rejected with 422", r.status_code == 422)

    deadline = time.time() + 5
    status = None
    while time.time() < deadline:
        r = client.get(f"/api/iqoo/tasks/{task_id}")
        status = r.json()["status"]
        if status in ("completed", "failed"):
            break
        time.sleep(0.05)
    check("Task reachable via GET and completes", status == "completed")

    r = client.get("/api/iqoo/tasks/does-not-exist")
    check("Unknown task_id returns 404", r.status_code == 404)

    r = client.post("/api/iqoo/tasks/does-not-exist/cancel")
    check("Cancel on unknown task_id returns 404", r.status_code == 404)

    r = client.post(f"/api/iqoo/tasks/{task_id}/retry")
    check("Retry on finished task returns 201... actually 200 with new record",
          r.status_code == 200 and r.json()["task_id"] != task_id)

    gateway.shutdown()


def main():
    test_task_store()
    test_event_bus()
    test_gateway_no_action_task()
    test_gateway_action_task()
    test_gateway_cancel_before_start()
    test_gateway_execution_failure()
    test_gateway_retry()
    test_gateway_unsupported_input_type()
    test_api_endpoints()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("iQOO Phase 1 (phone task gateway) offline logic verified.")


if __name__ == "__main__":
    main()
