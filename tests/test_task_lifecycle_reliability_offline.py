"""
Offline regression tests for Phase 2 (task lifecycle / retry / recovery
hardening).

Covers:
1. TaskOutcome -- the str-subclass that lets run_task()/run_planned_task()
   report an honest status without changing the plain-string return
   contract every existing caller and test already relies on.
2. _is_repeating_failed_action -- action-identity repetition detection,
   complementing _is_stagnant's observation-text comparison (Phase 1 made
   failed observations descriptive rather than a bare repeated
   self-report, so pure text comparison alone can miss a loop that's
   genuinely stuck on one action).
3. Honest status at every run_task()/run_planned_task() exit point --
   in particular, that reaching the natural end of a task/plan is no
   longer, by itself, reported as success if a step never verified.
4. interfaces/api/gateway.py's mapping of the fuller status vocabulary
   onto the existing completed/failed/cancelled terminal states that both
   the frontend (interfaces/desktop/src/api/types.ts's IqooPhase /
   TERMINAL_PHASES) and the backend (task_store.TERMINAL_STATUSES) are
   already closed over.

Usage:
    python3 tests/test_task_lifecycle_reliability_offline.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.react_loop import (  # noqa: E402
    ReactLoop, TaskOutcome,
    STATUS_SUCCESS, STATUS_FAILED, STATUS_STOPPED_AFTER_RETRIES,
    STATUS_UNABLE_TO_VERIFY, STATUS_CANCELLED,
)
from interfaces.api.task_store import TERMINAL_STATUSES  # noqa: E402
from interfaces.api.gateway import _OUTCOME_TO_GATEWAY_STATUS  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


class FakeSettings:
    vision_model = "moondream"
    ollama_host = "http://localhost:11434"
    primary_model = "qwen"


class FakeResp:
    def __init__(self, text, action=None, action_payload=None):
        self.text = text
        self.action = action
        self.action_payload = action_payload


def _make_loop():
    return ReactLoop(FakeSettings())


FOUND_OK = "Clicked on 'X' at (1, 2); it's no longer visible in the same " \
           "spot afterward, consistent with the click taking effect."
NOT_FOUND = "Could not find 'X' on screen"  # a real Verifier failure signal


# ─── TaskOutcome ─────────────────────────────────────────────────────────

def test_task_outcome_behaves_as_a_plain_string():
    outcome = TaskOutcome("Stopped after repeated failures.", STATUS_STOPPED_AFTER_RETRIES)
    check("Is a real str (isinstance)", isinstance(outcome, str))
    check("Equality compares as plain text", outcome == "Stopped after repeated failures.")
    check("Substring search works", "repeated failures" in outcome)
    check("f-string formatting embeds the text, not a repr", f"{outcome}" == str(outcome))
    check(".status carries the extra distinction", outcome.status == STATUS_STOPPED_AFTER_RETRIES)
    check("A derived string (e.g. .lower()) is a plain str, not TaskOutcome",
          type(outcome.lower()) is str)


def test_task_outcome_survives_sqlite_and_dataclass_field_assignment():
    import sqlite3
    import dataclasses
    outcome = TaskOutcome("Done.", STATUS_SUCCESS)

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (outcome TEXT)")
    conn.execute("INSERT INTO t VALUES (?)", (outcome,))
    conn.commit()
    row = conn.execute("SELECT outcome FROM t").fetchone()
    check("Round-trips through sqlite3 parameter binding intact", row[0] == "Done.")

    @dataclasses.dataclass
    class Resp:
        text: str

    r2 = dataclasses.replace(Resp(text="original"), text=outcome)
    check("dataclasses.replace() onto a str-typed field keeps the status",
          r2.text.status == STATUS_SUCCESS)


# ─── Action-repetition detection ────────────────────────────────────────

def test_action_key_identity():
    a = {"action": "control", "payload": {"type": "click", "description": "X"}}
    b = {"action": "control", "payload": {"type": "click", "description": "X"}}
    c = {"action": "control", "payload": {"type": "click", "description": "Y"}}
    check("Same action+payload produce the same key",
          ReactLoop._action_key(a) == ReactLoop._action_key(b))
    check("Different payload produces a different key",
          ReactLoop._action_key(a) != ReactLoop._action_key(c))
    check("A step with no action returns None (never counts as a repeat)",
          ReactLoop._action_key({"action": None, "payload": {}}) is None)
    check("Falls back to planned-step 'description' when 'payload' is absent",
          ReactLoop._action_key({"action": "control", "description": "click X"}) is not None)


def test_is_repeating_failed_action():
    loop = _make_loop()
    same_failed = [
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
    ]
    check("Same action failing 3x in a row is flagged",
          loop._is_repeating_failed_action(same_failed) is True)

    one_succeeded = [
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": True},
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
    ]
    check("Not flagged if any of the recent attempts actually verified fine",
          loop._is_repeating_failed_action(one_succeeded) is False)

    different_actions = [
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
        {"action": "control", "payload": {"type": "click", "description": "X"}, "success": False},
        {"action": "control", "payload": {"type": "type", "text": "VS Code"}, "success": False},
    ]
    check("Not flagged when the failing actions actually differ",
          loop._is_repeating_failed_action(different_actions) is False)

    check("Not flagged with fewer than the stagnation window's worth of steps",
          loop._is_repeating_failed_action(same_failed[:2]) is False)


def test_last_action_unresolved():
    loop = _make_loop()
    check("Empty observations -> nothing unresolved",
          loop._last_action_unresolved([]) is False)
    check("Last (and only) action succeeded -> nothing unresolved",
          loop._last_action_unresolved([{"attempts": [1], "success": True}]) is False)
    check("Last action failed -> flagged",
          loop._last_action_unresolved([{"attempts": [1], "success": False}]) is True)
    check("An earlier failure followed by a later, different action that "
          "succeeded is a recovery, not an unresolved failure",
          loop._last_action_unresolved(
              [{"attempts": [1], "success": False}, {"attempts": [1], "success": True}]
          ) is False)
    check("An earlier success followed by a later failure IS unresolved",
          loop._last_action_unresolved(
              [{"attempts": [1], "success": True}, {"attempts": [1], "success": False}]
          ) is True)
    check("Trailing text-only steps (no attempts) are skipped -- checks "
          "the last *executed* action, not just the last list entry",
          loop._last_action_unresolved(
              [{"attempts": [1], "success": False}, {"attempts": None, "success": True}]
          ) is True)


# ─── run_task: honest status at every exit point ────────────────────────

def test_run_task_clean_success():
    loop = _make_loop()

    class Brain:
        def __init__(self):
            self.calls = 0

        def process(self, session):
            self.calls += 1
            if self.calls == 1:
                return FakeResp("working on it", action="control", action_payload={"type": "click"})
            return FakeResp("All done.", action=None)

    with patch.object(loop, "execute", return_value=FOUND_OK):
        outcome = loop.run_task("do a thing", Brain(), SimpleNamespace())
    check("Clean completion returns success status", outcome.status == STATUS_SUCCESS)
    check("Text is the Brain's own completion message", outcome == "All done.")


def test_run_task_reports_failed_when_brain_gives_up_after_a_failure():
    """The Brain deciding 'no more action needed' does not by itself mean
    the task succeeded -- if the one action it took never verified, the
    honest status is failed, not success, even though the loop ended
    'normally'."""
    loop = _make_loop()

    class Brain:
        def __init__(self):
            self.calls = 0

        def process(self, session):
            self.calls += 1
            if self.calls == 1:
                return FakeResp("trying", action="control", action_payload={"type": "click"})
            return FakeResp("I couldn't find it, giving up.", action=None)

    with patch.object(loop, "execute", return_value=NOT_FOUND):
        outcome = loop.run_task("click something", Brain(), SimpleNamespace())
    check("A normal-looking completion after an unresolved failure is "
          "reported as failed, not success", outcome.status == STATUS_FAILED)


def test_run_task_cancelled():
    loop = _make_loop()
    cancel_event = SimpleNamespace(is_set=lambda: True)
    outcome = loop.run_task("do a thing", brain=object(), session=SimpleNamespace(),
                             cancel_event=cancel_event)
    check("Cancellation is reported distinctly, not as failure",
          outcome.status == STATUS_CANCELLED)


def test_run_task_stagnation_status():
    loop = _make_loop()

    class Brain:
        def process(self, session):
            return FakeResp("trying again", action="browser", action_payload={})

    with patch.object(loop, "execute", return_value="No content found"):
        outcome = loop.run_task("find something", Brain(), SimpleNamespace())
    check("Observation-text stagnation reports stopped_after_retries",
          outcome.status == STATUS_STOPPED_AFTER_RETRIES)


def test_run_task_action_repetition_status():
    """The new detection path: varying observation text (Phase 1's richer
    failure descriptions), identical failing action, should still stop
    early instead of burning all MAX_STEPS -- this is exactly the gap
    _is_stagnant alone doesn't cover once observations aren't bare
    repeated self-reports."""
    loop = _make_loop()

    class Brain:
        def __init__(self):
            self.calls = 0

        def process(self, session):
            self.calls += 1
            return FakeResp("typing again", action="control",
                             action_payload={"type": "type", "text": "VS Code"})

    call_count = {"n": 0}

    def varying_failure(action, payload):
        call_count["n"] += 1
        return (f"Typed: VS Code. Screen now shows: could not find any "
                f"matching results yet (check #{call_count['n']}).")

    with patch.object(loop, "execute", side_effect=varying_failure):
        outcome = loop.run_task("open VS Code", Brain(), SimpleNamespace())
    check("Repeating the identical FAILING action stops early even though "
          "the observation text keeps varying",
          outcome.status == STATUS_STOPPED_AFTER_RETRIES)
    check("Stops well before exhausting MAX_STEPS", call_count["n"] < 20)


def test_run_task_recovers_from_a_transient_failure():
    """TEST C analog: an action fails even after its own retry, a
    *different* action succeeds next -- this must NOT be misread as a
    stuck repeat (different payload, and it's not 3-in-a-row), and the
    task should complete as a genuine success."""
    loop = _make_loop()

    class Brain:
        def __init__(self):
            self.calls = 0

        def process(self, session):
            self.calls += 1
            if self.calls == 1:
                return FakeResp("clicking", action="control",
                                 action_payload={"type": "click", "description": "X"})
            if self.calls == 2:
                return FakeResp("trying a different spot", action="control",
                                 action_payload={"type": "click", "description": "Y"})
            return FakeResp("Got it, done.", action=None)

    # X's own attempt + its one retry both fail; Y then succeeds first try.
    responses = iter([NOT_FOUND, NOT_FOUND, FOUND_OK])
    with patch.object(loop, "execute", side_effect=lambda a, p: next(responses)):
        outcome = loop.run_task("click the right thing", Brain(), SimpleNamespace())
    check("Recovering via a different action reaches success",
          outcome.status == STATUS_SUCCESS)


def test_run_task_max_steps_status():
    loop = _make_loop()

    class Brain:
        def __init__(self):
            self.n = 0

        def process(self, session):
            self.n += 1
            # A different payload each time -> never trips action-repetition.
            return FakeResp(f"step {self.n}", action="control",
                             action_payload={"type": "click", "description": f"target {self.n}"})

    def varying_success(action, payload):
        # Different text each call too -> never trips observation-based
        # stagnation either, so this genuinely exercises MAX_STEPS rather
        # than aborting early via either detector.
        target = payload.get("description", "?")
        return f"Clicked on '{target}'; it's no longer visible, consistent with success."

    with patch.object(loop, "execute", side_effect=varying_success):
        outcome = loop.run_task("an endless task", Brain(), SimpleNamespace())
    check("Exhausting MAX_STEPS without a clear success or stuck-signal "
          "reports unable_to_verify", outcome.status == STATUS_UNABLE_TO_VERIFY)


# ─── run_planned_task: the "ran to the end but never verified" gap ──────

def test_run_planned_task_reports_failed_if_last_step_never_verified():
    """The concrete Phase 2 gap: previously, running through every planned
    step -- regardless of whether any of them actually verified --
    returned as if it had gone fine."""
    loop = _make_loop()
    plan = [
        {"step": 1, "description": "open search"},
        {"step": 2, "description": "click the result"},
    ]

    class Brain:
        def __init__(self):
            self.calls = 0

        def process(self, session):
            self.calls += 1
            return FakeResp(f"step {self.calls}", action="control",
                             action_payload={"type": "click", "description": f"s{self.calls}"})

    # Step 1 succeeds first try. Step 2 fails both its own attempt and its
    # one retry, ending the plan with its last step unresolved.
    responses = iter([FOUND_OK, NOT_FOUND, NOT_FOUND])
    with patch.object(loop, "_looks_multi_step", return_value=True), \
         patch("agent.react_loop.planner.decompose", return_value=plan), \
         patch.object(loop, "execute", side_effect=lambda a, p: next(responses)):
        outcome = loop.run_planned_task("do a multi-step thing", Brain(), SimpleNamespace())
    check("Plan finishing with its last step unverified is reported failed",
          outcome.status == STATUS_FAILED)


def test_run_planned_task_clean_success():
    loop = _make_loop()
    plan = [{"step": 1, "description": "open search"}, {"step": 2, "description": "click result"}]

    class Brain:
        def __init__(self):
            self.calls = 0

        def process(self, session):
            self.calls += 1
            return FakeResp(f"step {self.calls}", action="control",
                             action_payload={"type": "click", "description": f"s{self.calls}"})

    with patch.object(loop, "_looks_multi_step", return_value=True), \
         patch("agent.react_loop.planner.decompose", return_value=plan), \
         patch.object(loop, "execute", return_value=FOUND_OK):
        outcome = loop.run_planned_task("do a multi-step thing", Brain(), SimpleNamespace())
    check("A plan whose every step verifies reports success",
          outcome.status == STATUS_SUCCESS)


def test_run_planned_task_cancelled():
    loop = _make_loop()
    plan = [{"step": 1, "description": "open search"}]
    cancel_event = SimpleNamespace(is_set=lambda: True)
    with patch.object(loop, "_looks_multi_step", return_value=True), \
         patch("agent.react_loop.planner.decompose", return_value=plan):
        outcome = loop.run_planned_task("do a thing", brain=object(), session=SimpleNamespace(),
                                         cancel_event=cancel_event)
    check("Cancelling a planned task reports cancelled, not failed",
          outcome.status == STATUS_CANCELLED)


def test_planned_step_prompt_nudges_after_a_failed_step():
    loop = _make_loop()
    plan = [{"step": 1, "description": "a"}, {"step": 2, "description": "b"}]
    failed_obs = [{"step": 1, "description": "a", "observation": NOT_FOUND, "success": False}]
    ok_obs = [{"step": 1, "description": "a", "observation": FOUND_OK, "success": True}]

    prompt_after_failure = loop._build_planned_step_prompt("task", plan, plan[1], failed_obs)
    prompt_after_success = loop._build_planned_step_prompt("task", plan, plan[1], ok_obs)
    check("Prompt nudges toward a different approach after a failed step",
          "choose a different approach" in prompt_after_failure)
    check("Prompt does not include the nudge after a successful step",
          "choose a different approach" not in prompt_after_success)


# ─── gateway.py: mapping the fuller status onto the closed vocabulary ───

def test_gateway_status_mapping_matches_backend_and_frontend_vocabulary():
    check("success maps to completed",
          _OUTCOME_TO_GATEWAY_STATUS.get("success") == "completed")
    check("cancelled maps to cancelled",
          _OUTCOME_TO_GATEWAY_STATUS.get("cancelled") == "cancelled")
    # The production call site does .get(status, "failed") -- replicate that
    # default here for the statuses that intentionally aren't in the dict.
    for status in (STATUS_FAILED, STATUS_STOPPED_AFTER_RETRIES, STATUS_UNABLE_TO_VERIFY):
        check(f"{status} defaults to failed (not passed through raw)",
              _OUTCOME_TO_GATEWAY_STATUS.get(status, "failed") == "failed")
    check("An unrecognized/missing status also safely defaults to failed",
          _OUTCOME_TO_GATEWAY_STATUS.get(None, "failed") == "failed")

    # Every value this mapping can ever produce must be a status the
    # backend's own task_store.TERMINAL_STATUSES already recognizes --
    # otherwise task_store's "once terminal, stays terminal" guard
    # wouldn't fire, and an orphaned/late write could re-open the task.
    possible_outputs = set(_OUTCOME_TO_GATEWAY_STATUS.values()) | {"failed"}
    check("Every value this mapping can produce is a recognized terminal "
          "status in task_store", possible_outputs <= TERMINAL_STATUSES)


def main():
    test_task_outcome_behaves_as_a_plain_string()
    test_task_outcome_survives_sqlite_and_dataclass_field_assignment()
    test_action_key_identity()
    test_is_repeating_failed_action()
    test_last_action_unresolved()
    test_run_task_clean_success()
    test_run_task_reports_failed_when_brain_gives_up_after_a_failure()
    test_run_task_cancelled()
    test_run_task_stagnation_status()
    test_run_task_action_repetition_status()
    test_run_task_recovers_from_a_transient_failure()
    test_run_task_max_steps_status()
    test_run_planned_task_reports_failed_if_last_step_never_verified()
    test_run_planned_task_clean_success()
    test_run_planned_task_cancelled()
    test_planned_step_prompt_nudges_after_a_failed_step()
    test_gateway_status_mapping_matches_backend_and_frontend_vocabulary()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Phase 2 (task lifecycle / retry / recovery hardening) fixes verified.")


if __name__ == "__main__":
    main()
