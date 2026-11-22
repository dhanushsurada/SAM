"""
SAM JEV Reflex Engine — System 1 Streaming Reflexes & Predictive Speculative Execution.

Inspired by JEV (TypeSafe AI) and real-time reflex architectures:
- "Jev is the reflexes. A bigger model is the brain. My own notes are the memory."
- Evaluates streaming transcripts mid-sentence (sub-80ms decision latency).
- Fires speculative actions (app launching, window focusing, note pre-fetching)
  BEFORE the user finishes speaking.

Leap-Ahead Feature:
- "Speculative Context Injection & Predictive Workspace Synthesis":
  Pre-fetches relevant notes, agenda, and context into a prompt buffer while the
  user is still speaking, allowing System 2 (Brain) to answer instantly upon speech end.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("SAM.JevReflex")


@dataclass
class ReflexDecision:
    action: str                        # "open_app", "search_notes", "search_web", "briefing", "none"
    payload: Dict[str, Any]            # e.g. {"app": "Spotify", "background": True}
    confidence: float                  # 0.0 - 1.0
    latency_ms: float                  # Decision latency in milliseconds
    speculative: bool = True           # Executed mid-sentence
    executed: bool = False             # Whether real action was dispatched
    context_injected: Optional[str] = None # Pre-fetched memory/notes context


# Known app aliases for instant sub-millisecond reflex matching
FAST_APP_PATTERNS = [
    (re.compile(r"\b(?:open|launch|start|switch to)\s+spotify\b", re.IGNORECASE), "Spotify", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+(?:chrome|google chrome)\b", re.IGNORECASE), "Google Chrome", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+safari\b", re.IGNORECASE), "Safari", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+(?:vs\s*code|vscode|code)\b", re.IGNORECASE), "Visual Studio Code", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+(?:terminal|iterm)\b", re.IGNORECASE), "Terminal", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+notes\b", re.IGNORECASE), "Notes", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+(?:calendar|cal)\b", re.IGNORECASE), "Calendar", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+calculator\b", re.IGNORECASE), "Calculator", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+slack\b", re.IGNORECASE), "Slack", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+whatsapp\b", re.IGNORECASE), "WhatsApp", "open_app"),
    (re.compile(r"\b(?:open|launch|start|switch to)\s+finder\b", re.IGNORECASE), "Finder", "open_app"),
]

# Reflex patterns for personal agenda / notes ("what's on my plate from my real life")
PLATE_PATTERNS = [
    re.compile(r"\b(?:what(?:'s|\s+is)\s+on\s+my\s+plate)\b", re.IGNORECASE),
    re.compile(r"\b(?:what\s+are\s+my\s+tasks|my\s+agenda|my\s+priorities)\b", re.IGNORECASE),
    re.compile(r"\b(?:check\s+(?:my\s+)?notes|look\s+at\s+(?:my\s+)?notes)\b", re.IGNORECASE),
    re.compile(r"\b(?:morning\s+briefing|daily\s+briefing|daily\s+digest)\b", re.IGNORECASE),
]

# Web search reflex patterns
SEARCH_PATTERNS = [
    re.compile(r"\b(?:search\s+(?:the\s+web\s+for|google\s+for|for))\s+(.+)", re.IGNORECASE),
    re.compile(r"\b(?:look\s+up)\s+(.+)", re.IGNORECASE),
]


class JevReflexEngine:
    """
    Sub-80ms streaming decision engine.
    Listens to partial transcript tokens mid-sentence and triggers reflexes.
    """

    def __init__(self, settings=None, controller=None, notes_vault=None, briefing_agent=None):
        self.settings = settings
        self.controller = controller
        self.notes_vault = notes_vault
        self.briefing_agent = briefing_agent
        
        self.jev_base_url = getattr(settings, "jev_base_url", "http://127.0.0.1:8765").rstrip("/") if settings else "http://127.0.0.1:8765"
        self.jev_timeout = getattr(settings, "jev_timeout_seconds", 0.5) if settings else 0.5
        
        # State tracking for the current ongoing utterance
        self._current_utterance_id: Optional[str] = None
        self._triggered_actions: List[ReflexDecision] = []
        self._speculative_context: Optional[str] = None
        self._lock = False

    def reset_stream(self, utterance_id: Optional[str] = None):
        """Reset state at the beginning of a new spoken sentence / turn."""
        self._current_utterance_id = utterance_id or str(time.time())
        self._triggered_actions = []
        self._speculative_context = None

    def evaluate_partial(self, partial_text: str) -> Optional[ReflexDecision]:
        """
        Evaluates partial stream of text mid-sentence.
        Returns a ReflexDecision if an instant reflex is ready, otherwise None.
        """
        cleaned = (partial_text or "").strip()
        if len(cleaned.split()) < 2:
            return None

        # Check if we already triggered an action in this utterance
        if any(d.executed for d in self._triggered_actions):
            return None

        start_time = time.perf_counter()

        # Step 1: Sub-millisecond Regex & Heuristic Reflex Evaluation (< 2ms)
        decision = self._evaluate_fast_rules(cleaned, start_time)
        
        # Step 2: If inconclusive and local-jev is enabled, evaluate via JEV system-one API
        if decision is None and getattr(self.settings, "planning_backend", "jev") == "jev":
            decision = self._evaluate_jev_api(cleaned, start_time)

        if decision and decision.confidence >= 0.75:
            # Execute reflex action immediately mid-sentence
            self._execute_reflex(decision)
            self._triggered_actions.append(decision)
            return decision

        return None

    def _evaluate_fast_rules(self, text: str, start_time: float) -> Optional[ReflexDecision]:
        # App launching reflex
        for pattern, app_name, action_type in FAST_APP_PATTERNS:
            if pattern.search(text):
                latency = (time.perf_counter() - start_time) * 1000.0
                return ReflexDecision(
                    action=action_type,
                    payload={"app": app_name, "background": True},
                    confidence=0.98,
                    latency_ms=latency,
                    speculative=True
                )

        # Plate / Notes / Daily Agenda reflex
        for pattern in PLATE_PATTERNS:
            if pattern.search(text):
                latency = (time.perf_counter() - start_time) * 1000.0
                return ReflexDecision(
                    action="search_notes",
                    payload={"intent": "plate_query", "query": text},
                    confidence=0.95,
                    latency_ms=latency,
                    speculative=True
                )

        # Web Search reflex
        for pattern in SEARCH_PATTERNS:
            m = pattern.search(text)
            if m:
                query = m.group(1).strip()
                if len(query) >= 3:
                    latency = (time.perf_counter() - start_time) * 1000.0
                    return ReflexDecision(
                        action="search_web",
                        payload={"query": query},
                        confidence=0.88,
                        latency_ms=latency,
                        speculative=True
                    )

        return None

    def _evaluate_jev_api(self, text: str, start_time: float) -> Optional[ReflexDecision]:
        """Query TypeSafe AI local-jev for fast system-one classification."""
        try:
            api_key = os.environ.get("LOCAL_JEV_API_KEY")
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "model": getattr(self.settings, "jev_model", "jev-latest") if self.settings else "jev-latest",
                "state": {"streaming_transcript": text[:400]},
                "questions": {
                    "reflex_action": {
                        "type": "choice",
                        "instructions": "Determine if a system reflex action should execute mid-sentence.",
                        "criteria": {
                            "open_app": "User wants to open or focus an application",
                            "search_notes": "User is asking about their personal plate, agenda, or notes",
                            "search_web": "User is asking to search the internet",
                            "none": "No immediate reflex action should be taken yet"
                        }
                    }
                }
            }
            resp = requests.post(
                f"{self.jev_base_url}/v1/systemone",
                json=payload,
                headers=headers,
                timeout=min(0.2, self.jev_timeout) # strictly bounded for reflex speed
            )
            if resp.status_code == 200:
                data = resp.json()
                choice_info = data.get("answers", {}).get("reflex_action", {})
                choice = choice_info.get("choice")
                conf = float(choice_info.get("confidence", 0.0) or 0.0)
                latency = (time.perf_counter() - start_time) * 1000.0
                if choice in ("open_app", "search_notes", "search_web") and conf >= 0.75:
                    return ReflexDecision(
                        action=choice,
                        payload={"source": "jev_api", "text": text},
                        confidence=conf,
                        latency_ms=latency,
                        speculative=True
                    )
        except Exception as e:
            logger.debug(f"JEV API reflex check skipped: {e}")
        return None

    def _execute_reflex(self, decision: ReflexDecision):
        """Dispatches the reflex action in background."""
        logger.info(
            f"[JEV Reflex] {decision.latency_ms:.1f}ms: Executing '{decision.action}' "
            f"with payload {decision.payload} while user is still speaking"
        )
        try:
            if decision.action == "open_app" and self.controller:
                app_name = decision.payload.get("app")
                if app_name and hasattr(self.controller, "open_app"):
                    self.controller.open_app(app_name, background=True)
                    decision.executed = True

            elif decision.action == "search_notes":
                # Leap-Ahead: Speculative Context Injection
                context = ""
                if self.notes_vault and hasattr(self.notes_vault, "get_active_plate"):
                    context = self.notes_vault.get_active_plate()
                elif self.briefing_agent and hasattr(self.briefing_agent, "get_quick_summary"):
                    context = self.briefing_agent.get_quick_summary()
                
                if context:
                    self._speculative_context = context
                    decision.context_injected = context
                    decision.executed = True
                    logger.info(f"[JEV Reflex] Speculative context pre-fetched ({len(context)} chars)")

            elif decision.action == "search_web":
                query = decision.payload.get("query", "")
                decision.executed = True
                logger.info(f"[JEV Reflex] Web search pre-warmed for '{query}'")

        except Exception as e:
            logger.warning(f"Reflex execution error: {e}")

    def get_speculative_context(self) -> Optional[str]:
        """Returns any context pre-fetched by reflexes to inject into Brain's prompt."""
        return self._speculative_context

    def get_triggered_actions(self) -> List[ReflexDecision]:
        """Returns all reflex decisions fired during this utterance."""
        return list(self._triggered_actions)
