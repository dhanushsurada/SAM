"""
SAM Tiered Execution Architecture — Performance Optimization Engine

Provides a 3-tier routing mechanism to eliminate unnecessary LLM calls and latency:
- Tier 1: Direct Deterministic Execution (sub-5ms, zero LLM calls)
- Tier 2: Fast Agent Execution (intent classification, simple single-step tools, device routing)
- Tier 3: Advanced Reasoning (deep multi-step planning, reflection, error recovery)
"""

import re
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple, List

logger = logging.getLogger("SAM.TieredRouter")


class ExecutionTier(str, Enum):
    DIRECT = "tier_1_direct"       # Deterministic execution, 0 LLM calls
    FAST = "tier_2_fast"           # Fast intent classification / simple tool
    ADVANCED = "tier_3_advanced"   # Deep planning / complex reasoning


@dataclass
class RouteDecision:
    tier: ExecutionTier
    action: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    target_device: Optional[str] = None  # "desktop" | "android" | None (auto-detect)
    confidence: float = 1.0
    reason: str = ""
    suggested_text: Optional[str] = None
    requires_planning: bool = False


# Known app aliases for direct launching
KNOWN_APP_MAP = {
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "safari": "Safari",
    "firefox": "Firefox",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "vs code": "Visual Studio Code",
    "visual studio code": "Visual Studio Code",
    "terminal": "Terminal",
    "iterm": "iTerm",
    "finder": "Finder",
    "calculator": "Calculator",
    "calc": "Calculator",
    "notes": "Notes",
    "settings": "System Settings",
    "system settings": "System Settings",
    "spotify": "Spotify",
    "slack": "Slack",
    "discord": "Discord",
    "mail": "Mail",
    "calendar": "Calendar",
    "messages": "Messages",
    "whatsapp": "WhatsApp",
    "telegram": "Telegram",
}

# Math calculation patterns (e.g. "calculate 2 + 2", "what is 50 * 3", "125 / 5")
CALC_PATTERN = re.compile(
    r"^(?:calculate|what is|compute|solve)?\s*([0-9\.\s\+\-\*\/\%\(\)\^]+)\s*$",
    re.IGNORECASE
)

# Open app patterns (e.g. "open Chrome", "launch Calculator")
OPEN_APP_PATTERN = re.compile(
    r"^(?:open|launch|start|switch to)\s+([a-zA-Z0-9\s\.\-_]+?)(?:\s+app|\s+application)?$",
    re.IGNORECASE
)

# Browse URL pattern
URL_PATTERN = re.compile(
    r"^(?:open|go to|browse to|visit)\s+(https?://[^\s]+|[a-zA-Z0-9\-]+\.(?:com|org|net|io|dev|edu|gov|app)[^\s]*)$",
    re.IGNORECASE
)

# Screenshot pattern
SCREENSHOT_PATTERN = re.compile(
    r"^(?:take\s+(?:a\s+)?screenshot|capture\s+(?:the\s+)?screen|screenshot)$",
    re.IGNORECASE
)

# Device target indicators
ANDROID_PREFIX_PATTERNS = [
    re.compile(r"^(?:on\s+(?:my\s+)?(?:phone|android|mobile)|phone|android):\s*(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:on|to)\s+(?:my\s+)?(?:phone|android|mobile)$", re.IGNORECASE),
]

DESKTOP_PREFIX_PATTERNS = [
    re.compile(r"^(?:on\s+(?:my\s+)?(?:computer|pc|desktop|mac)|desktop|mac):\s*(.+)$", re.IGNORECASE),
    re.compile(r"^(.+?)\s+(?:on|to)\s+(?:my\s+)?(?:computer|pc|desktop|mac)$", re.IGNORECASE),
]

# Multi-step conjunctions that necessitate Tier 3 planning
MULTI_STEP_SIGNALS = [
    " and then ", " then ", " after that ", " followed by ",
    " first ", " next ", " secondly ", " finally "
]


class TieredExecutionRouter:
    """
    Evaluates commands and assigns them to the lowest required execution tier,
    minimizing token latency and resource consumption.
    """

    def __init__(self, settings=None):
        self.settings = settings

    def route(self, user_input: str) -> RouteDecision:
        cleaned = (user_input or "").strip()
        if not cleaned:
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action=None,
                suggested_text="I didn't hear anything.",
                reason="Empty input"
            )

        # Check for explicit device prefixing or suffixing
        target_device = None
        command_body = cleaned

        for pat in ANDROID_PREFIX_PATTERNS:
            m = pat.match(cleaned)
            if m:
                target_device = "android"
                command_body = m.group(1).strip()
                break

        if not target_device:
            for pat in DESKTOP_PREFIX_PATTERNS:
                m = pat.match(cleaned)
                if m:
                    target_device = "desktop"
                    command_body = m.group(1).strip()
                    break

        lower_body = command_body.lower()

        # Check if task is explicitly multi-step
        if any(signal in f" {lower_body} " for signal in MULTI_STEP_SIGNALS):
            return RouteDecision(
                tier=ExecutionTier.ADVANCED,
                target_device=target_device,
                requires_planning=True,
                reason="Multi-step signals detected"
            )

        # ─── TIER 1: DETERMINISTIC CHECKS (0 LLM Calls) ──────────────────────

        # 1. Calculation
        calc_match = CALC_PATTERN.match(command_body)
        if calc_match:
            expr = calc_match.group(1).strip()
            # Verify expression contains at least one math operator
            if any(op in expr for op in ["+", "-", "*", "/", "%", "**", "//"]):
                # Validate characters
                if all(c in "0123456789. +-/*%()^" for c in expr):
                    return RouteDecision(
                        tier=ExecutionTier.DIRECT,
                        action="calculate",
                        action_payload={"expression": expr},
                        target_device=target_device or "desktop",
                        confidence=1.0,
                        reason="Deterministic math expression",
                        suggested_text=f"Calculating {expr}."
                    )

        # 2. Screenshot
        if SCREENSHOT_PATTERN.match(command_body):
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action="control",
                action_payload={"type": "screenshot"},
                target_device=target_device or "desktop",
                confidence=1.0,
                reason="Deterministic screenshot command",
                suggested_text="Taking a screenshot."
            )

        # 3. Direct URL browsing
        url_match = URL_PATTERN.match(command_body)
        if url_match:
            raw_url = url_match.group(1).strip()
            if not raw_url.startswith("http://") and not raw_url.startswith("https://"):
                full_url = f"https://{raw_url}"
            else:
                full_url = raw_url
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action="browser",
                action_payload={"url": full_url, "task": f"navigate to {full_url}"},
                target_device=target_device or "desktop",
                confidence=1.0,
                reason="Deterministic URL navigation",
                suggested_text=f"Opening {full_url}."
            )

        # 4. Open Application
        open_match = OPEN_APP_PATTERN.match(command_body)
        if open_match:
            app_raw = open_match.group(1).strip().lower()
            resolved_app = KNOWN_APP_MAP.get(app_raw, open_match.group(1).strip())
            
            # If target device is Android or command is phone-specific:
            if target_device == "android":
                return RouteDecision(
                    tier=ExecutionTier.DIRECT,
                    action="app_launch",
                    action_payload={"app": resolved_app},
                    target_device="android",
                    confidence=1.0,
                    reason="Deterministic Android app launch",
                    suggested_text=f"Opening {resolved_app} on your phone."
                )
            else:
                return RouteDecision(
                    tier=ExecutionTier.DIRECT,
                    action="control",
                    action_payload={"type": "open_app", "app": resolved_app},
                    target_device="desktop",
                    confidence=1.0,
                    reason="Deterministic desktop app launch",
                    suggested_text=f"Opening {resolved_app}."
                )

        # 5. Mobile notification query
        if target_device == "android" or "phone notification" in lower_body or "notifications on my phone" in lower_body:
            return RouteDecision(
                tier=ExecutionTier.FAST,
                action="get_notifications",
                action_payload={},
                target_device="android",
                confidence=0.9,
                reason="Android notification inspection",
                suggested_text="Checking notifications on your phone."
            )

        # ─── TIER 2: FAST CLASSIFICATION / SINGLE STEP ───────────────────────
        # Commands with unambiguous single intent, e.g. search query, read doc
        if lower_body.startswith("search for ") or lower_body.startswith("find document "):
            return RouteDecision(
                tier=ExecutionTier.FAST,
                target_device=target_device or "desktop",
                reason="Single tool search intent"
            )

        # ─── TIER 3: COMPLEX / AMBIGUOUS REASONING ───────────────────────────
        return RouteDecision(
            tier=ExecutionTier.ADVANCED,
            target_device=target_device,
            requires_planning=len(command_body.split()) > 15,
            reason="General reasoning or ambiguous prompt"
        )
