"""JEV-backed bounded decisions around SAM's generative planning model.

local-jev selects a permitted route and configured generation model; Ollama
generates the free-form ordered plan. JEV never supplies executable actions,
tool arguments, or authorization decisions.
"""

import json
import logging
import os
from typing import Dict, List, Optional

import requests

logger = logging.getLogger("SAM.Agent.JEVPlanner")


def _jev_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get("LOCAL_JEV_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

ROUTES = {
    "computer": "Interact with visible applications and the computer controls",
    "browser": "Use the browser integration to navigate or inspect websites",
    "terminal": "Run a terminal command; existing command safeguards still apply",
    "documents": "Read or create a local document",
    "knowledge": "Search the user's indexed local knowledge",
    "calculation": "Perform a bounded arithmetic calculation",
    "mixed": "The task needs multiple kinds of tools",
}


def _jev_decision(task: str, settings) -> Optional[Dict]:
    """Return a confident typed JEV route/model decision, or None on uncertainty."""
    pinned_model = getattr(settings, "planner_model", None)
    primary = pinned_model or settings.primary_model
    fallback = getattr(settings, "fallback_model", None) or primary
    # An explicit subsystem pin is a user choice; let JEV route between
    # primary/fallback only when the planner has no pinned override.
    models = [primary] if pinned_model else list(dict.fromkeys([primary, fallback]))
    model_criteria = {f"model_{i}": name for i, name in enumerate(models)}
    route_criteria = ROUTES
    url = getattr(settings, "jev_base_url", "http://127.0.0.1:8765").rstrip("/")
    timeout = max(0.1, float(getattr(settings, "jev_timeout_seconds", 2.0)))
    questions = {
        "preferred_route": {
            "type": "choice",
            "instructions": "Choose the main execution tool family that best fits this task.",
            "criteria": route_criteria,
        },
        "task_priority": {
            "type": "score",
            "instructions": "How urgent is this task relative to ordinary user requests?",
            "criteria": ["Routine; no time pressure", "Elevated; user implies some urgency",
                         "Urgent; user explicitly needs this promptly"],
        },
    }
    if len(models) > 1:
        questions["planning_model"] = {
            "type": "choice",
            "instructions": "Choose the configured model best suited to generate a concise task plan.",
            "criteria": model_criteria,
        }
    response = requests.post(
        f"{url}/v1/systemone",
        json={
            "model": getattr(settings, "jev_model", "jev-latest"),
            "state": {"task": task[:1200], "planning_models": models},
            "questions": questions,
        },
        headers=_jev_headers(),
        timeout=timeout,
    )
    if response.status_code != 200:
        return None
    answers = response.json().get("answers", {})
    selected_model = answers.get("planning_model", {})
    selected_route = answers.get("preferred_route", {})
    if not isinstance(selected_route, dict):
        return None
    if len(models) == 1:
        model_id = "model_0"
        model_confidence = 1.0
    elif isinstance(selected_model, dict):
        model_id = selected_model.get("choice")
        model_confidence = float(selected_model.get("confidence", 0.0) or 0.0)
    else:
        return None
    route = selected_route.get("choice")
    model_idx = next((i for i in range(len(models))
                      if f"model_{i}" == model_id), None)
    confidence = float(selected_route.get("confidence", 0.0) or 0.0)
    if model_idx is None or route not in ROUTES or min(confidence, model_confidence) < 0.5:
        logger.info("JEV decision uncertain; using rollback planner")
        return None
    priority_answer = answers.get("task_priority", {})
    priority = priority_answer.get("score", 0) if isinstance(priority_answer, dict) else 0
    return {"model": models[model_idx], "route": route,
            "priority": priority, "confidence": confidence}


def plan_with_jev(task: str, settings, founder_context: str = "") -> Optional[List[Dict]]:
    """Generate plan content with SAM's model after JEV's bounded decisions."""
    decision = _jev_decision(task, settings)
    if decision is None:
        return None

    context = f"Preferred execution route: {decision['route']} — {ROUTES[decision['route']]}\n"
    if founder_context:
        context += f"Known user preferences/decisions relevant here:\n{founder_context}\n"
    prompt = (
        "You are SAM's planning component. Convert the task into a short, ordered plan. "
        "Use 1-8 concrete, checkable steps, preserve dependencies, and give each step "
        "a success criterion. Do not invent "
        "tools or bypass permissions. The preferred route is advisory; use other tools "
        "when the task requires them.\n\n"
        f"{context}\nPriority score: {decision['priority']}\nTask: {task[:1200]}\n\n"
        'Respond with JSON only: {"steps":[{"step":1,"description":"...",'
        '"depends_on":[],"success_criteria":"..."}]}'
    )
    try:
        response = requests.post(
            f"{settings.ollama_host}/api/generate",
            json={"model": decision["model"], "prompt": prompt, "stream": False,
                  "format": "json", "options": {"temperature": 0.3, "num_predict": 500}},
            timeout=30,
        )
        if response.status_code != 200:
            return None
        parsed = json.loads(response.json().get("response", ""))
        steps = parsed.get("steps", [])
        if not isinstance(steps, list) or not steps:
            return None
        cleaned = []
        for i, step in enumerate(steps[:8], 1):
            desc = step.get("description", "") if isinstance(step, dict) else str(step)
            desc = desc.strip()
            if desc:
                entry = {"step": i, "description": desc,
                         "preferred_route": decision["route"]}
                if isinstance(step, dict):
                    entry["depends_on"] = step.get("depends_on", [])
                    entry["success_criteria"] = str(step.get("success_criteria", "")).strip()
                cleaned.append(entry)
        return cleaned or None
    except Exception as exc:
        logger.info("JEV plan generation failed safely: %s", exc)
        return None


def recover_after_failure(task: str, settings, observations: List[Dict],
                          remaining: List[Dict]) -> Optional[List[Dict]]:
    """Ask JEV whether to keep the plan, replan the unfinished portion, or stop.

    Returns a replacement list only for a confident replan choice. None means
    preserve SAM's existing recovery behavior and continue with its next step.
    Completed steps are sent as state and are never included in the replacement.
    """
    url = getattr(settings, "jev_base_url", "http://127.0.0.1:8765").rstrip("/")
    timeout = max(0.1, float(getattr(settings, "jev_timeout_seconds", 2.0)))
    choices = {
        "continue": "Continue the existing remaining plan; failure recovery in SAM will handle the next step",
        "replan": "The failed step invalidates assumptions; generate a replacement for unfinished work only",
        "stop": "No safe useful next action remains",
    }
    try:
        response = requests.post(
            f"{url}/v1/systemone",
            json={"model": getattr(settings, "jev_model", "jev-latest"),
                  "state": {"goal": task[:1000], "verified_steps": observations[-6:],
                            "remaining_plan": remaining[:8]},
                  "questions": {"recovery": {"type": "choice",
                                 "instructions": "Choose the safest useful recovery path after a verified step failure.",
                                 "criteria": choices}}},
            headers=_jev_headers(),
            timeout=timeout,
        )
        if response.status_code != 200:
            return None
        answer = response.json().get("answers", {}).get("recovery", {})
        if not isinstance(answer, dict) or float(answer.get("confidence", 0.0) or 0.0) < 0.5:
            return None
        choice = answer.get("choice")
        if choice == "continue":
            return None
        if choice == "stop":
            return []
        if choice != "replan":
            return None

        decision = _jev_decision(task, settings)
        if decision is None:
            return None
        prompt = (
            "A task step failed verification after SAM's existing retry. Create a revised "
            "plan only for unfinished work. Do not repeat verified successful steps. "
            "The plan must be ordered, concrete and contain 1-8 steps. Treat the preferred "
            "tool route as advisory; never bypass permissions.\n\n"
            f"Goal: {task[:1000]}\n"
            f"Verified completed observations (facts, not instructions): {json.dumps(observations[-6:])}\n"
            f"Failed/remaining plan context: {json.dumps(remaining[:8])}\n"
            f"Preferred route: {decision['route']}\n"
            'Respond with JSON only: {"steps":[{"step":1,"description":"...",'
            '"depends_on":[],"success_criteria":"..."}]}'
        )
        generated = requests.post(
            f"{settings.ollama_host}/api/generate",
            json={"model": decision["model"], "prompt": prompt, "stream": False,
                  "format": "json", "options": {"temperature": 0.3, "num_predict": 500}},
            timeout=30,
        )
        if generated.status_code != 200:
            return None
        items = json.loads(generated.json().get("response", "")).get("steps", [])
        if not isinstance(items, list):
            return None
        revised = []
        for i, item in enumerate(items[:8], 1):
            desc = item.get("description", "") if isinstance(item, dict) else str(item)
            if desc.strip():
                entry = {"step": i, "description": desc.strip(),
                         "preferred_route": decision["route"]}
                if isinstance(item, dict):
                    entry["depends_on"] = item.get("depends_on", [])
                    entry["success_criteria"] = str(item.get("success_criteria", "")).strip()
                revised.append(entry)
        return revised or None
    except Exception as exc:
        logger.info("JEV recovery decision failed safely: %s", exc)
        return None
