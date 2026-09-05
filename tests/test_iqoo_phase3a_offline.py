"""
OFFLINE test suite for iQOO Phase 3A (reliability & recovery).

Everything here is offline: no real Ollama, no real faster-whisper, no
real phone, no real Office Kit. Covers: SSE backlog/reconnect (via the
server module's event_stream generator directly, and via EventBus
unit tests already extended in test_iqoo_phase1_offline.py), task
timeout, worker recovery from an uncaught exception, retry safety
(stale-cancellation avoidance, non-terminal retry rejection, retried_from
history), server-restart orphan recovery, demo reset (including the
busy-refusal guard), and expanded health diagnostics.

Usage:
    HOME=/tmp/sam_iqoo_phase3a_test python3 tests/test_iqoo_phase3a_offline.py
"""

import sqlite3
import sys
import time
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import patch

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


def make_mocked_gateway(task_timeout_seconds=600):
    """Same construction pattern as the Phase 1/2 offline suites,
    duplicated locally per the existing repo convention of independent
    per-phase test files. task_timeout_seconds is exposed so the timeout
    test doesn't have to wait for the real 600s default."""
    with patch("memory.identity.Identity") as MockIdentity, \
         patch("memory.retrieve.MemoryRetriever") as MockMemory, \
         patch("founder_mode.manager.FounderModeManager") as MockFounder, \
         patch("core.brain.Brain") as MockBrain, \
         patch("agent.react_loop.ReactLoop") as MockReactLoop, \
         patch("interfaces.api.gateway.VisionAdapter") as MockVision, \
         patch("interfaces.api.gateway.AudioAdapter") as MockAudio:

        MockIdentity.return_value.load.return_value = {}
        MockMemory.return_value.retrieve.return_value = []
        MockMemory.return_value.get_store.return_value = None
        MockFounder.return_value.get_context.return_value = ""
        MockFounder.return_value.capture_if_relevant.return_value = None
        MockBrain.return_value._check_ollama.return_value = True
        MockVision.return_value.model_available.return_value = True
        MockAudio.return_value.whisper_installed.return_value = True

        from config.settings import Settings
        settings = Settings()
        settings.incognito = True

        from interfaces.api.gateway import TaskGateway
        gateway = TaskGateway(settings=settings, task_timeout_seconds=task_timeout_seconds)
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


def wait_until(predicate, timeout=5.0, interval=0.05):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# ─── B/C: Task timeout, worker recovery ────────────────────────────────────

def test_task_timeout_reports_promptly_and_does_not_get_clobbered():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway(
        task_timeout_seconds=0.2)
    try:
        release = {"go": False}

        def slow_process(session):
            # Sleeps far longer than the timeout, then eventually
            # "completes" — simulating a real stuck call that
            # eventually, unhelpfully, returns success after the fact.
            while not release["go"]:
                time.sleep(0.02)
            return FakeBrainResponse(text="finally done", action=None)

        mock_brain.process.side_effect = slow_process

        start = time.time()
        task_id = gateway.submit_task("do something slow")
        final = wait_for_status(gateway, task_id, {"failed"}, timeout=2.0)
        elapsed = time.time() - start

        check("Timeout reports failure well before a real long hang would resolve",
              final == "failed" and elapsed < 1.5)
        record = gateway.get_task(task_id)
        check("Timeout error message is specific, not generic",
              "timed out" in (record["error"] or "").lower())

        # Now let the orphaned thread actually finish and try to report
        # "completed" — the terminal-status guard (task_store.py) must
        # prevent this from clobbering the timeout failure the phone
        # already saw.
        release["go"] = True
        time.sleep(0.5)
        record_after = gateway.get_task(task_id)
        check("Late completion from the orphaned thread does not overwrite the timeout failure",
              record_after["status"] == "failed" and "timed out" in (record_after["error"] or "").lower())

        events = gateway.event_bus.get_since(task_id, after_seq=0)
        terminal_events = [e for e in events if e["phase"] in ("completed", "failed", "cancelled")]
        check("Exactly one terminal event exists even though the orphaned thread finished late",
              len(terminal_events) == 1 and terminal_events[0]["phase"] == "failed")
    finally:
        gateway.shutdown()


def test_worker_recovery_task_a_fails_task_b_still_executes():
    """The exact scenario named in the PDR: 'task A fails, task B still
    executes.' Forces an exception to escape _process_task entirely
    (not just be caught by its own inner try/except) by making
    task_store.get_cancel_event raise once — this exercises the
    belt-and-suspenders catch added to _run_task_with_timeout's _run()
    closure, which was a real gap found while writing this test (see
    interfaces/api/gateway.py's comment at that catch site)."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        task_a = gateway.submit_task("task A")

        original_get_cancel_event = gateway.task_store.get_cancel_event
        call_count = {"n": 0}

        def flaky_get_cancel_event(task_id):
            call_count["n"] += 1
            if task_id == task_a and call_count["n"] == 1:
                raise RuntimeError("simulated crash reading cancel state")
            return original_get_cancel_event(task_id)

        gateway.task_store.get_cancel_event = flaky_get_cancel_event

        final_a = wait_for_status(gateway, task_a, {"completed", "failed"}, timeout=3.0)
        check("Task A reaches a terminal state despite an uncaught internal exception",
              final_a == "failed")
        record_a = gateway.get_task(task_a)
        check("Task A's failure reason reflects the actual crash",
              "simulated crash" in (record_a["error"] or ""))

        # Restore normal behavior and confirm the worker thread is still
        # alive and able to process a completely unrelated task B.
        gateway.task_store.get_cancel_event = original_get_cancel_event
        mock_brain.process.return_value = FakeBrainResponse(text="task B done", action=None)
        task_b = gateway.submit_task("task B")
        final_b = wait_for_status(gateway, task_b, {"completed", "failed"}, timeout=3.0)
        check("Task B still executes normally after task A's crash", final_b == "completed")
        check("Worker thread survived task A's crash", gateway._worker.is_alive())
    finally:
        gateway.shutdown()


def test_queue_continues_after_timeout():
    """Explicit check for PDR requirement C: 'allow the queue to
    continue' after a timeout — with the honest, documented caveat that
    continuation happens once the orphaned thread actually finishes
    (see ARCHITECTURE.md), not instantly. Verifies the queued-behind
    task still runs to completion."""
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway(
        task_timeout_seconds=0.2)
    try:
        release = {"go": False}
        call_log = []

        def controlled_process(session):
            call_log.append(session.user_input)
            if session.user_input == "stuck task":
                while not release["go"]:
                    time.sleep(0.02)
                return FakeBrainResponse(text="stuck task eventually finished", action=None)
            return FakeBrainResponse(text="quick task done", action=None)

        mock_brain.process.side_effect = controlled_process

        stuck_id = gateway.submit_task("stuck task")
        quick_id = gateway.submit_task("quick task")

        stuck_final = wait_for_status(gateway, stuck_id, {"failed"}, timeout=2.0)
        check("Stuck task times out", stuck_final == "failed")

        # quick_id is still queued behind the orphaned thread at this
        # point (single-worker invariant preserved) — release it now.
        release["go"] = True
        quick_final = wait_for_status(gateway, quick_id, {"completed", "failed"}, timeout=3.0)
        check("Queue continues: the task behind a timed-out one still completes",
              quick_final == "completed")
    finally:
        gateway.shutdown()


# ─── D/E: Retry safety ──────────────────────────────────────────────────────

def test_retry_rejects_non_terminal_task():
    from interfaces.api.gateway import TaskAlreadyActiveError

    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        release = {"go": False}

        def slow_process(session):
            while not release["go"]:
                time.sleep(0.01)
            return FakeBrainResponse(text="done", action=None)

        mock_brain.process.side_effect = slow_process
        task_id = gateway.submit_task("still running")
        wait_until(lambda: gateway.get_task(task_id)["status"] == "understanding", timeout=2.0)

        try:
            gateway.retry_task(task_id)
            check("Retrying a still-active task is rejected", False)
        except TaskAlreadyActiveError:
            check("Retrying a still-active task is rejected", True)

        release["go"] = True
        wait_for_status(gateway, task_id, {"completed", "failed"})
    finally:
        gateway.shutdown()


def test_retry_records_history_and_fresh_cancel_state():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_brain.process.return_value = FakeBrainResponse(text="ok", action=None)
        original_id = gateway.submit_task("do the thing")
        wait_for_status(gateway, original_id, {"completed", "failed"})

        gateway.cancel_task(original_id)  # no-op since already terminal, but exercise it anyway
        new_id = gateway.retry_task(original_id)
        new_record = gateway.get_task(new_id)

        check("Retry records retried_from for debugging history",
              new_record["retried_from"] == original_id)
        check("Retry's cancel_event starts fresh, not reusing the original's state",
              not gateway.task_store.get_cancel_event(new_id).is_set())

        final = wait_for_status(gateway, new_id, {"completed", "failed"})
        check("Retried task completes normally with a clean cancel state",
              final == "completed")
    finally:
        gateway.shutdown()


# ─── A/F: Server restart recovery, demo reset ──────────────────────────────

def test_orphaned_task_recovery_on_restart():
    from interfaces.api.task_store import TaskStore, ORPHAN_ERROR_MESSAGE

    store = TaskStore()
    task_id = store.create_task("left running when the process died", "text", [])
    store.update_status(task_id, "executing")  # simulate a task mid-flight

    check("Task is non-terminal before 'restart'", store.get_task(task_id)["status"] == "executing")

    # A brand-new TaskStore instance against the same DB simulates a
    # fresh process starting up after a crash/restart.
    fresh_store = TaskStore()
    recovered = fresh_store.recover_orphaned_tasks()

    check("Orphaned task_id is reported as recovered", task_id in recovered)
    record = fresh_store.get_task(task_id)
    check("Orphaned task is marked failed, not left executing forever", record["status"] == "failed")
    check("Orphaned task's error message is specific to server-restart recovery",
          record["error"] == ORPHAN_ERROR_MESSAGE)

    # A task that already reached a terminal status before "restart"
    # must NOT be touched by recovery.
    completed_id = store.create_task("already done", "text", [])
    store.update_status(completed_id, "completed", result_text="fine")
    fresh_store2 = TaskStore()
    recovered2 = fresh_store2.recover_orphaned_tasks()
    check("Already-terminal tasks are not falsely recovered", completed_id not in recovered2)


def test_gateway_recovers_orphans_at_startup():
    from interfaces.api.task_store import TaskStore

    store = TaskStore()
    orphan_id = store.create_task("orphaned before gateway starts", "text", [])
    store.update_status(orphan_id, "planning")

    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        record = gateway.get_task(orphan_id)
        check("TaskGateway.__init__ recovers pre-existing orphaned tasks automatically",
              record["status"] == "failed")
    finally:
        gateway.shutdown()


def test_demo_reset_clears_state_and_respects_busy_guard():
    from interfaces.api.gateway import DemoResetBusyError

    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_brain.process.return_value = FakeBrainResponse(text="ok", action=None)
        task_id = gateway.submit_task("a finished task")
        wait_for_status(gateway, task_id, {"completed", "failed"})
        check("Task exists before reset", gateway.get_task(task_id) is not None)
        check("Event history exists before reset", len(gateway.event_bus.get_since(task_id)) > 0)

        deleted = gateway.reset_demo_state()
        check("Reset reports at least one deleted task", deleted >= 1)
        check("Task no longer exists after reset", gateway.get_task(task_id) is None)
        check("Event history is cleared after reset", gateway.event_bus.get_since(task_id) == [])

        # Busy guard: reset must refuse while a task is active.
        release = {"go": False}

        def slow_process(session):
            while not release["go"]:
                time.sleep(0.01)
            return FakeBrainResponse(text="done", action=None)

        mock_brain.process.side_effect = slow_process
        busy_id = gateway.submit_task("still going")
        wait_until(lambda: gateway.get_task(busy_id)["status"] == "understanding", timeout=2.0)

        try:
            gateway.reset_demo_state()
            check("Reset refuses while a task is active", False)
        except DemoResetBusyError:
            check("Reset refuses while a task is active", True)

        release["go"] = True
        wait_for_status(gateway, busy_id, {"completed", "failed"})

        # Now idle again — reset should succeed.
        deleted2 = gateway.reset_demo_state()
        check("Reset succeeds again once idle", deleted2 >= 1)
    finally:
        gateway.shutdown()


def test_demo_reset_never_touches_memory_or_founder_mode():
    """Static/structural check: TaskStore.reset_demo_state and
    EventBus.reset_all must not import or reference memory.store or
    founder_mode anywhere in their actual code — confirmed via the AST
    (so multi-line docstring prose explaining the design decision, which
    legitimately mentions both by name, can never accidentally trip this
    check the way a plain substring/line search would)."""
    import ast
    import inspect
    from interfaces.api.task_store import TaskStore
    from interfaces.api.events import EventBus

    def references_forbidden_module(func) -> bool:
        import textwrap
        source = textwrap.dedent(inspect.getsource(func))
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any("memory" in a.name or "founder_mode" in a.name for a in node.names):
                    return True
            elif isinstance(node, ast.ImportFrom):
                if node.module and ("memory" in node.module or "founder_mode" in node.module):
                    return True
            elif isinstance(node, ast.Attribute):
                if node.attr in ("memory", "founder_mode", "get_store"):
                    return True
        return False

    for func in (TaskStore.reset_demo_state, EventBus.reset_all):
        check(f"{func.__qualname__}'s actual code never touches memory/founder_mode",
              not references_forbidden_module(func))


# ─── G: Health diagnostics ──────────────────────────────────────────────────

def test_health_reports_expanded_diagnostics():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        health = gateway.health()
        check("Health reports worker_alive", health["worker_alive"] is True)
        check("Health reports brain_reachable", health["brain_reachable"] is True)
        check("Health reports vision_model_available", health["vision_model_available"] is True)
        check("Health reports whisper_available", health["whisper_available"] is True)
        check("Health reports uptime_seconds as a non-negative number", health["uptime_seconds"] >= 0)
        check("Health status is 'ok' when everything is healthy", health["status"] == "ok")
        check("Health does not leak task instruction content",
              "instruction" not in health and "result_text" not in health)

        mock_brain._check_ollama.return_value = False
        health_degraded = gateway.health()
        check("Health degrades to 'degraded' when the brain is unreachable",
              health_degraded["status"] == "degraded")
        check("vision_model_available is None (not False) when brain is unreachable — distinct meaning",
              health_degraded["vision_model_available"] is None)
    finally:
        gateway.shutdown()


def test_health_reports_worker_dead_after_shutdown():
    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    gateway.shutdown()
    wait_until(lambda: not gateway._worker.is_alive(), timeout=2.0)
    health = gateway.health()
    check("Health reports worker_alive False after shutdown", health["worker_alive"] is False)
    check("Health status is 'degraded' once the worker is dead", health["status"] == "degraded")


# ─── A: SSE reconnect (server module's event_stream generator) ────────────

def test_sse_event_stream_reconnect_no_duplicates():
    import asyncio
    from interfaces.api import server as server_module

    gateway, mock_brain, mock_react_loop, mock_vision, mock_audio = make_mocked_gateway()
    try:
        mock_brain.process.return_value = FakeBrainResponse(text="all good", action=None)
        task_id = gateway.submit_task("do a thing")
        wait_for_status(gateway, task_id, {"completed", "failed"})

        async def consume(after_seq):
            chunks = []
            async for chunk in server_module.event_stream(gateway, task_id, after_seq, request=None):
                chunks.append(chunk)
            return chunks

        # Cold reconnect (after_seq=0): full backlog including the
        # terminal event.
        full = asyncio.run(consume(0))
        check("Cold SSE reconnect (after_seq=0) replays the terminal event",
              any('"phase": "completed"' in c for c in full))
        check("Each SSE chunk carries an `id:` line for Last-Event-ID reconnect support",
              all(c.startswith("id: ") for c in full))

        # Reconnect with a Last-Event-ID matching the very last event —
        # must not re-render anything (no duplicates).
        last_seq = gateway.event_bus.latest_seq(task_id)
        resumed = asyncio.run(consume(last_seq))
        check("Reconnecting already caught-up (Last-Event-ID == latest) yields zero duplicate chunks",
              resumed == [])

        # Reconnect from partway through must only get the remainder,
        # not the events already seen.
        first_seq = 1
        partial = asyncio.run(consume(first_seq))
        check("Partial reconnect (after_seq=1) never re-sends event #1",
              not any('"seq": 1,' in c for c in partial))
    finally:
        gateway.shutdown()


def main():
    print("=== Timeout & worker recovery ===")
    test_task_timeout_reports_promptly_and_does_not_get_clobbered()
    test_worker_recovery_task_a_fails_task_b_still_executes()
    test_queue_continues_after_timeout()

    print("\n=== Retry safety ===")
    test_retry_rejects_non_terminal_task()
    test_retry_records_history_and_fresh_cancel_state()

    print("\n=== Server-restart recovery & demo reset ===")
    test_orphaned_task_recovery_on_restart()
    test_gateway_recovers_orphans_at_startup()
    test_demo_reset_clears_state_and_respects_busy_guard()
    test_demo_reset_never_touches_memory_or_founder_mode()

    print("\n=== Health diagnostics ===")
    test_health_reports_expanded_diagnostics()
    test_health_reports_worker_dead_after_shutdown()

    print("\n=== SSE reconnect ===")
    test_sse_event_stream_reconnect_no_duplicates()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("iQOO Phase 3A (reliability & recovery) offline logic verified.")
    print("NOTE: no real Ollama, faster-whisper, phone, or Office Kit hardware")
    print("was used anywhere in this suite. Server-restart simulation uses a")
    print("fresh TaskStore instance against the same on-disk DB, not an actual")
    print("process restart.")


if __name__ == "__main__":
    main()
