"""Offline compatibility checks for the JEV planning adapter."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import importlib.util
import types

sys.path.insert(0, str(Path(__file__).parent.parent))

# SAM declares requests as a runtime dependency. Keep this focused offline
# test runnable in minimal environments by supplying a stub that every test
# call replaces with a mock.
if importlib.util.find_spec("requests") is None:
    requests_stub = types.ModuleType("requests")
    requests_stub.post = lambda *args, **kwargs: None
    requests_stub.get = lambda *args, **kwargs: None
    sys.modules["requests"] = requests_stub

from agent.jev_planner import plan_with_jev, recover_after_failure  # noqa: E402
from agent.react_loop import ReactLoop  # noqa: E402


def _response(payload, status=200):
    result = MagicMock()
    result.status_code = status
    result.json.return_value = payload
    return result


def _jev_answers(route="browser", model="model_0", confidence=0.9):
    return {"answers": {
        "planning_model": {"choice": model, "confidence": confidence},
        "preferred_route": {"choice": route, "confidence": confidence},
        "task_priority": {"score": 1.0},
    }}


def test_jev_decisions_and_generative_plan():
    settings = SimpleNamespace(
        planning_backend="jev", jev_base_url="http://127.0.0.1:8765",
        jev_model="jev-latest", jev_timeout_seconds=1,
        primary_model="local-primary", fallback_model="local-fallback",
        planner_model=None, ollama_host="http://localhost:11434",
    )
    with patch("agent.jev_planner.requests.post", side_effect=[
        _response(_jev_answers()),
        _response({"response": json.dumps({"steps": [
            {"step": 1, "description": "Open the browser"},
            {"step": 2, "description": "Search for the page"},
        ]})}),
    ]) as post:
        plan = plan_with_jev("open browser then search", settings)
    assert len(plan) == 2
    assert plan[0]["preferred_route"] == "browser"
    assert "Priority score: 1.0" in post.call_args_list[1].kwargs["json"]["prompt"]
    assert post.call_args_list[1].kwargs["json"]["model"] == "local-primary"


def test_jev_uncertainty_fails_closed_to_legacy_path():
    from agent import planner
    settings = SimpleNamespace(planning_backend="jev", jev_base_url="http://127.0.0.1:8765",
                               jev_model="jev-latest", jev_timeout_seconds=1,
                               primary_model="m", fallback_model="m", planner_model=None,
                               ollama_host="http://localhost:11434")
    with patch("agent.jev_planner.requests.post", return_value=_response(_jev_answers(confidence=0.2))), \
         patch.object(planner, "decompose_legacy", return_value=[{"step": 1, "description": "legacy"}]) as legacy:
        result = planner.decompose("do work", settings)
    assert result[0]["description"] == "legacy"
    legacy.assert_called_once()


def test_unavailable_jev_uses_rollback_planner():
    from agent import planner
    settings = SimpleNamespace(planning_backend="jev", jev_base_url="http://127.0.0.1:8765",
                               jev_model="jev-latest", jev_timeout_seconds=1,
                               primary_model="m", fallback_model="m", planner_model=None,
                               ollama_host="http://localhost:11434")
    with patch("agent.jev_planner.requests.post", side_effect=ConnectionError("service offline")), \
         patch.object(planner, "decompose_legacy", return_value=[{"step": 1, "description": "legacy"}]) as legacy:
        result = planner.decompose("do work", settings)
    assert result[0]["description"] == "legacy"
    legacy.assert_called_once()


def test_explicit_planner_model_pin_is_preserved():
    from agent.jev_planner import _jev_decision
    settings = SimpleNamespace(planner_model="pinned-planner", primary_model="primary",
                               fallback_model="fallback", jev_base_url="http://127.0.0.1:8765",
                               jev_model="jev-latest", jev_timeout_seconds=1)
    response = _response({"answers": {
        "preferred_route": {"choice": "terminal", "confidence": 0.9},
        "task_priority": {"score": 1.0},
    }})
    with patch("agent.jev_planner.requests.post", return_value=response) as post:
        decision = _jev_decision("run task", settings)
    assert decision["model"] == "pinned-planner"
    questions = post.call_args.kwargs["json"]["questions"]
    assert "planning_model" not in questions


def test_recovery_replans_from_verified_state_and_unfinished_steps():
    settings = SimpleNamespace(jev_base_url="http://127.0.0.1:8765", jev_model="jev-latest",
                               jev_timeout_seconds=1, ollama_host="http://localhost:11434")
    observations = [{"step": 1, "description": "completed", "success": True,
                     "observation": "done"},
                    {"step": 2, "description": "failed", "success": False,
                     "observation": "could not find item"}]
    remaining = [{"step": 3, "description": "old future step"}]
    with patch("agent.jev_planner.requests.post", side_effect=[
        _response({"answers": {"recovery": {"choice": "replan", "confidence": 0.9}}}),
        _response({"response": json.dumps({"steps": [
            {"description": "replacement for unfinished work", "depends_on": [1],
             "success_criteria": "target is visible"}
        ]})}),
    ]) as post, patch("agent.jev_planner._jev_decision", return_value={
        "model": "local-primary", "route": "browser", "priority": 1, "confidence": 0.9
    }):
        replacement = recover_after_failure("complete the task", settings, observations, remaining)
    assert replacement[0]["description"] == "replacement for unfinished work"
    assert replacement[0]["success_criteria"] == "target is visible"
    recovery_state = post.call_args_list[0].kwargs["json"]["state"]
    assert recovery_state["verified_steps"] == observations
    assert recovery_state["remaining_plan"] == remaining


class _BrainResponse:
    def __init__(self, action=None):
        self.text = "Done"
        self.action = action
        self.action_payload = {}


class _Brain:
    def __init__(self):
        self.prompts = []
        self.responses = []

    def process(self, session):
        self.prompts.append(session.user_input)
        return self.responses.pop(0) if self.responses else _BrainResponse()


def test_failed_step_replans_only_remaining_steps():
    settings = SimpleNamespace(planning_backend="jev")
    loop = ReactLoop(settings)
    loop._safe_reflect = lambda *args, **kwargs: None
    brain = _Brain()
    brain.responses = [_BrainResponse(action="control")]
    loop._execute_verified = MagicMock(side_effect=[
        {"observation": "could not find target", "success": False, "attempts": [{"attempt": 1}]},
        {"observation": "revised action succeeded", "success": True, "attempts": [{"attempt": 1}]},
    ])
    first = _BrainResponse(action="control")
    plan = [{"step": 1, "description": "Try original action"},
            {"step": 2, "description": "Old remaining work"}]
    revised = [{"step": 1, "description": "Revised unfinished work"}]
    with patch("agent.react_loop.planner.decompose", return_value=plan), \
         patch("agent.jev_planner.recover_after_failure", return_value=revised) as recover:
        outcome = loop.run_planned_task("first then second", brain, SimpleNamespace(user_input=""),
                                        initial_response=first)
    assert outcome.status == "success"
    assert any("Revised unfinished work" in prompt for prompt in brain.prompts), brain.prompts
    assert all("Old remaining work" not in prompt for prompt in brain.prompts)
    assert recover.call_args.args[2][0]["success"] is False


def test_successful_steps_do_not_trigger_replanning():
    loop = ReactLoop(SimpleNamespace(planning_backend="jev"))
    loop._safe_reflect = lambda *args, **kwargs: None
    plan = [{"step": 1, "description": "First"}, {"step": 2, "description": "Second"}]
    with patch("agent.react_loop.planner.decompose", return_value=plan), \
         patch("agent.jev_planner.recover_after_failure") as recover:
        result = loop.run_planned_task("first then second", _Brain(), SimpleNamespace(user_input=""))
    assert result.status == "success"
    recover.assert_not_called()


if __name__ == "__main__":
    for test in (test_jev_decisions_and_generative_plan,
                 test_jev_uncertainty_fails_closed_to_legacy_path,
                 test_unavailable_jev_uses_rollback_planner,
                 test_explicit_planner_model_pin_is_preserved,
                 test_recovery_replans_from_verified_state_and_unfinished_steps,
                 test_failed_step_replans_only_remaining_steps,
                 test_successful_steps_do_not_trigger_replanning):
        test()
        print(f"PASS {test.__name__}")
