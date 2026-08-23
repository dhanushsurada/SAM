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
    imports) since gateway.py imports them lazily inside __init__.

    Also mocks VisionAdapter/AudioAdapter (added in Phase 2) so nothing
    in this Phase 1 suite can accidentally reach a real Ollama/Whisper
    call over the network — by default both raise clearly if invoked,
    since no test in *this* file is meant to exercise real perception
    logic (that's tests/test_iqoo_phase2_offline.py's job)."""
    with patch("memory.identity.Identity") as MockIdentity, \
         patch("memory.retrieve.MemoryRetriever") as MockMemory, \
         patch("founder_mode.manager.FounderModeManager") as MockFounder, \
         patch("core.brain.Brain") as MockBrain, \
         patch("agent.react_loop.ReactLoop") as MockReactLoop, \
         patch("iqoo.gateway.VisionAdapter") as MockVision, \
         patch("iqoo.gateway.AudioAdapter") as MockAudio:

        MockIdentity.return_value.load.return_value = {}
        MockMemory.return_value.retrieve.return_value = []
        MockMemory.return_value.get_store.return_value = None
        MockFounder.return_value.get_context.return_value = ""
        MockFounder.return_value.capture_if_relevant.return_value = None
        MockBrain.return_value._check_ollama.return_value = True

        def _unexpected_vision_call(*a, **kw):
            raise AssertionError(
                "VisionAdapter.interpret() was called from the Phase 1 suite — "
                "perception behavior belongs in test_iqoo_phase2_offline.py")

        def _unexpected_audio_call(*a, **kw):
            raise AssertionError(
                "AudioAdapter.transcribe() was called from the Phase 1 suite — "
                "perception behavior belongs in test_iqoo_phase2_offline.py")

        MockVision.return_value.interpret.side_effect = _unexpected_vision_call
        MockAudio.return_value.transcribe.side_effect = _unexpected_audio_call

        from config.settings import Settings
        settings = Settings()
        settings.incognito = True  # skip session.save() entirely in tests

        from iqoo.gateway import TaskGateway
        gateway = TaskGateway(settings=settings)
        return gateway, MockBrain.return_value, MockReactLoop.return_value, \
            MockVision.return_value, MockAudio.return_value


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
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
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
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
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


def test_gateway_cancel_before_start_emits_exactly_one_terminal_event():
    """Explicit regression check (requested in review): a pre-start
    cancellation — cancel_task() called while the task is still queued,
    never reaching brain.process() — must publish exactly one terminal
    'cancelled' event on the task's event queue, not zero and not more
    than one. Reviewed iqoo/gateway.py's early-cancellation branch
    (the `if cancel_event.is_set(): ... return` guard at the top of
    _process_task) line by line and via a programmatic duplicate-line
    scan; only a single event_bus.publish(..., "cancelled", ...) call
    exists there. This test locks that invariant in so a future edit
    can't silently reintroduce a duplicate."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        slow_holder = {"go": False}

        def slow_process(session):
            while not slow_holder["go"]:
                time.sleep(0.01)
            return FakeBrainResponse(text="done", action=None)

        mock_brain.process.side_effect = slow_process
        blocker_id = gateway.submit_task("slow task")
        target_id = gateway.submit_task("cancel me before start")

        # Subscribe to the target task's event queue BEFORE cancelling,
        # so every event it emits (including "received" from submit_task
        # and the eventual "cancelled") is captured for counting.
        q = gateway.event_bus.subscribe_queue(target_id)

        ok = gateway.cancel_task(target_id)
        check("Cancel accepted while task still queued", ok is True)

        slow_holder["go"] = True
        wait_for_status(gateway, blocker_id, {"completed", "failed"})
        final = wait_for_status(gateway, target_id, {"completed", "failed", "cancelled"})
        check("Pre-start cancellation resolves to cancelled", final == "cancelled")

        # Drain every event published for this task_id.
        events = []
        while True:
            try:
                events.append(q.get_nowait())
            except Exception:
                break

        cancelled_events = [e for e in events if e["phase"] == "cancelled"]
        check("Exactly one 'cancelled' event was published for a pre-start cancellation",
              len(cancelled_events) == 1)
        check("The single cancelled event has the expected message",
              cancelled_events and cancelled_events[0]["message"] == "Cancelled before execution started")

        # Brain must never have been reached for the cancelled task
        # specifically (it was called once, for the unrelated blocker
        # task, which is fine and expected).
        check("Brain was called exactly once (only for the blocker task, not the cancelled one)",
              mock_brain.process.call_count == 1)
    finally:
        gateway.shutdown()


def test_gateway_cancel_before_start():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
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
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_brain.process.side_effect = RuntimeError("ollama unreachable")
        task_id = gateway.submit_task("do something")
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Brain exception reported as failed, not silently dropped", final == "failed")
        check("Error message captured", "ollama unreachable" in (record["error"] or ""))
    finally:
        gateway.shutdown()


def test_gateway_concurrency_serialization():
    """Explicit test for the invariant documented in ARCHITECTURE.md:
    SAM's Hands aren't safe for concurrent execution, so TaskGateway must
    run tasks one at a time off its single worker thread, no matter how
    many are submitted back to back. This proves it directly by tracking
    concurrent-entry count into the mocked Brain.process call, instead of
    only inferring serialization indirectly from cancel-before-start
    timing (test_gateway_cancel_before_start)."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        active = {"count": 0, "max": 0}
        lock = __import__("threading").Lock()
        order = []

        def tracked_process(session):
            with lock:
                active["count"] += 1
                active["max"] = max(active["max"], active["count"])
            order.append(("start", session.user_input))
            time.sleep(0.15)  # long enough to overlap if serialization is broken
            order.append(("end", session.user_input))
            with lock:
                active["count"] -= 1
            return FakeBrainResponse(text=f"done: {session.user_input}", action=None)

        mock_brain.process.side_effect = tracked_process

        task_ids = [gateway.submit_task(f"task {i}") for i in range(4)]
        for task_id in task_ids:
            final = wait_for_status(gateway, task_id, {"completed", "failed"}, timeout=5.0)
            check(f"Task {task_id[:8]} reached a terminal status", final == "completed")

        check("Never more than one task executing Brain.process concurrently",
              active["max"] == 1)
        check("All four tasks actually ran", len(order) == 8)

        # Each task's start/end pair must be contiguous — no interleaving
        # of "task N start" ... "task M start" before "task N end".
        non_interleaved = True
        running = None
        for kind, label in order:
            if kind == "start":
                if running is not None:
                    non_interleaved = False
                running = label
            else:  # end
                if running != label:
                    non_interleaved = False
                running = None
        check("Task execution order is strictly serialized (no interleaving)",
              non_interleaved)
    finally:
        gateway.shutdown()


def test_gateway_retry():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
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


def test_gateway_perception_failure_handled_gracefully():
    """Phase 1 regression check, updated for Phase 2: a non-text task
    used to always fail with a hardcoded 'Phase 2' message (Phase 1
    behavior). Now that Phase 2 actually wires VisionAdapter/AudioAdapter
    into _perceive(), this test instead confirms the gateway still fails
    a task cleanly (not a crash, not a hang) when perception itself
    raises — using the mocked adapter from make_mocked_gateway() rather
    than a real network call, keeping this suite fully offline. Detailed
    multimodal behavior (valid image, valid audio, structured context
    composition, etc.) is covered in test_iqoo_phase2_offline.py."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        from iqoo.errors import PerceptionError
        mock_vision.interpret.side_effect = PerceptionError("mock vision failure")

        task_id = gateway.submit_task(
            "turn this into a backend", input_type="image+text",
            attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": "..."}]
        )
        final = wait_for_status(gateway, task_id, {"completed", "failed"})
        record = gateway.get_task(task_id)
        check("Perception failure fails the task cleanly, not silently",
              final == "failed" and "mock vision failure" in (record["error"] or ""))
        check("Brain is never reached when perception fails first",
              not mock_brain.process.called)
    finally:
        gateway.shutdown()


def test_api_endpoints():
    from fastapi.testclient import TestClient
    import iqoo.server as server_module

    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
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
    test_gateway_cancel_before_start_emits_exactly_one_terminal_event()
    test_gateway_concurrency_serialization()
    test_gateway_execution_failure()
    test_gateway_retry()
    test_gateway_perception_failure_handled_gracefully()
    test_api_endpoints()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("iQOO Phase 1 (phone task gateway) offline logic verified.")


if __name__ == "__main__":
    main()
