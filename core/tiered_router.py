"""
SAM Tiered Execution Architecture — Performance Optimization Engine

Provides a 3-tier routing mechanism to eliminate unnecessary LLM calls and latency:
- Tier 1: Direct Deterministic Execution (sub-5ms, zero LLM calls)
- Tier 2: Fast Agent Execution (intent classification, simple single-step tools, device routing)
- Tier 3: Advanced Reasoning (deep multi-step planning, reflection, error recovery)
"""

import re
import logging
import urllib.request
import urllib.parse
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


# Instant greeting responses (sub-millisecond conversational replies)
GREETING_RESPONSES = {
    "hi": "Hey! I'm SAM, your personal AI assistant. What would you like to do?",
    "hello": "Hello! I'm SAM. How can I help you today?",
    "hey": "Hey there! Ready to help. What's on your mind?",
    "hey sam": "Hey! I'm listening. What do you need?",
    "heysam": "Hey! I'm here. How can I help?",
    "hi sam": "Hi! Ready when you are.",
    "hello sam": "Hello! What can I do for you?",
    "good morning": "Good morning! Ready for today's tasks.",
    "good afternoon": "Good afternoon! How can I assist you?",
    "good evening": "Good evening! What can I help you with?",
    "what's up": "All systems nominal! What's up with you?",
    "whats up": "All systems nominal! What's up with you?",
    "sup": "Ready when you are. What's the plan?",
    "how are you": "Running smooth and fast! What can I do for you?",
    "how are you doing": "Doing great, fully local and ready. What do you need?",
    "who are you": "I'm SAM, your personal sovereign AI assistant. I run fully on your machine to manage tasks, execute commands, control your apps, and assist you.",
    "what is your name": "My name is SAM — your Sovereign AI Manager.",
    "who made you": "I was created by Dhanush as a personal AI assistant.",
    "what can you do": "I can launch and close apps, play music and videos on YouTube, search the web, calculate math, take screenshots, manage files, and coordinate tasks with your phone.",
    "thanks": "You got it! Let me know if you need anything else.",
    "thank you": "Glad to help! Anything else on your mind?",
    "bye": "Goodbye! Just say 'Hey SAM' whenever you need me.",
    "goodbye": "See you later! Have a great day.",
    "help": "You can ask me to open or close apps (e.g. 'open Chrome', 'close Safari'), play songs ('play aya sher on youtube'), take screenshots ('take a screenshot on desktop'), solve math, or answer questions."
}


def resolve_youtube_play_url(query: str) -> Tuple[str, str]:
    """
    Directly resolves the top video ID for a YouTube query in sub-200ms
    using a fast search scrape, avoiding slow multi-step browser hallucinations.
    """
    clean_query = query.strip()
    encoded = urllib.parse.quote_plus(clean_query)
    search_url = f"https://www.youtube.com/results?search_query={encoded}"
    try:
        req = urllib.request.Request(
            search_url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=2.5) as response:
            html = response.read().decode("utf-8", errors="ignore")
            video_ids = re.findall(r"/watch\?v=([a-zA-Z0-9_-]{11})", html)
            if video_ids:
                first_video = f"https://www.youtube.com/watch?v={video_ids[0]}"
                return first_video, f"Playing '{clean_query}' on YouTube"
    except Exception as e:
        logger.debug(f"Direct YouTube query resolution fallback: {e}")
    return search_url, f"Opening YouTube search for '{clean_query}'"


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

# Close app patterns (e.g. "close Chrome", "quit Safari")
CLOSE_APP_PATTERN = re.compile(
    r"^(?:close|quit|kill|stop|terminate|exit)\s+([a-zA-Z0-9\s\.\-_]+?)(?:\s+app|\s+application)?$",
    re.IGNORECASE
)

# YouTube play pattern (e.g. "open youtube and play aya sher song", "play believer on youtube")
YOUTUBE_PLAY_PATTERN = re.compile(
    r"^(?:open\s+youtube\s+and\s+play\s+(.+)|play\s+(.+?)(?:\s+(?:on|in)\s+youtube)?|watch\s+(.+?)(?:\s+(?:on|in)\s+youtube)?|search\s+youtube\s+for\s+(.+))$",
    re.IGNORECASE
)

# Browse URL pattern
URL_PATTERN = re.compile(
    r"^(?:open|go to|browse to|visit)\s+(https?://[^\s]+|[a-zA-Z0-9\-]+\.(?:com|org|net|io|dev|edu|gov|app)[^\s]*)$",
    re.IGNORECASE
)

# Screenshot pattern (including desktop destination)
SCREENSHOT_PATTERN = re.compile(
    r"^(?:take\s+(?:a\s+)?screenshot|capture\s+(?:the\s+)?screen|screenshot)(?:.*)?$",
    re.IGNORECASE
)

# Messaging patterns (e.g. 'open whatsapp and text “Rey” to Steve pn clg', 'text "hello" to John', 'text Alice "Good morning"')
MESSAGING_PATTERN_TO = re.compile(
    r"^(?:open\s+(?:whatsapp|messages)\s+and\s+)?(?:text|send\s+(?:a\s+)?(?:whatsapp\s+)?message(?:\s+to)?|message)\s+(?:[\"“'](.+?)[\"”']|([^\s].+?))\s+to\s+(.+?)(?:\s+on\s+(?:whatsapp|messages))?$",
    re.IGNORECASE
)
MESSAGING_PATTERN_DIRECT = re.compile(
    r"^(?:open\s+(?:whatsapp|messages)\s+and\s+)?(?:text|message)\s+([a-zA-Z0-9\s]+?)(?:\s+on\s+(?:whatsapp|messages))?(?:\s+(?:saying|with|that))?\s+[\"“'](.+?)[\"”'](?:\s+on\s+(?:whatsapp|messages))?$",
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

        # 1. Instant Conversational Greetings & Identity queries (<1ms)
        clean_punct = re.sub(r"[^\w\s]", "", lower_body).strip()
        if clean_punct in GREETING_RESPONSES:
            reply_text = GREETING_RESPONSES[clean_punct]
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action="greet",
                target_device="desktop",
                confidence=1.0,
                reason="Direct conversational greeting",
                suggested_text=reply_text
            )

        # 2. YouTube Music / Video Direct Playback
        yt_match = YOUTUBE_PLAY_PATTERN.match(command_body)
        if yt_match:
            song_or_query = next((g for g in yt_match.groups() if g), "").strip()
            if song_or_query:
                # Clean filler words
                clean_query = re.sub(r"^(?:the\s+)?song\s+", "", song_or_query, flags=re.IGNORECASE).strip()
                direct_url, desc = resolve_youtube_play_url(clean_query)
                return RouteDecision(
                    tier=ExecutionTier.DIRECT,
                    action="browser",
                    action_payload={
                        "url": direct_url,
                        "task": f"Playing '{clean_query}' on YouTube",
                        "use_system_browser": True
                    },
                    target_device=target_device or "desktop",
                    confidence=1.0,
                    reason="Deterministic YouTube media playback",
                    suggested_text=f"Playing '{clean_query}' on YouTube: {direct_url}"
                )

        # 3. Direct Messaging (WhatsApp / Messages)
        msg_match = MESSAGING_PATTERN_TO.match(command_body)
        msg_content = ""
        recipient = ""
        if msg_match:
            msg_content = (msg_match.group(1) or msg_match.group(2) or "").strip()
            recipient = (msg_match.group(3) or "").strip()
        else:
            dir_match = MESSAGING_PATTERN_DIRECT.match(command_body)
            if dir_match:
                recipient = (dir_match.group(1) or "").strip()
                msg_content = (dir_match.group(2) or "").strip()

        if msg_content and recipient:
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action="control",
                action_payload={
                    "type": "send_message",
                    "app": "WhatsApp",
                    "recipient": recipient,
                    "message": msg_content,
                },
                target_device="desktop",
                confidence=1.0,
                reason="Deterministic WhatsApp messaging",
                suggested_text=f"Sent WhatsApp message '{msg_content}' to {recipient}."
            )

        # 4. Calculation
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

        # 4. Screenshot
        ss_match = SCREENSHOT_PATTERN.match(command_body)
        if ss_match:
            dest = "desktop" if ("desktop" in lower_body or "desktop" in cleaned.lower() or "reels" in lower_body) else "default"
            folder = None
            if "reels" in lower_body or "reels" in cleaned.lower():
                folder = "Reels"
            folder_text = f"/{folder}" if folder else ""
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action="control",
                action_payload={"type": "screenshot", "destination": dest, "folder": folder},
                target_device=target_device or "desktop",
                confidence=1.0,
                reason="Deterministic screenshot command",
                suggested_text=f"Taking a screenshot and saving to Desktop{folder_text}." if dest == "desktop" else "Taking a screenshot."
            )

        # 5. Direct URL browsing
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
                action_payload={"url": full_url, "task": f"navigate to {full_url}", "use_system_browser": True},
                target_device=target_device or "desktop",
                confidence=1.0,
                reason="Deterministic URL navigation",
                suggested_text=f"Opening {full_url}."
            )

        # 6. Close / Quit Application
        close_match = CLOSE_APP_PATTERN.match(command_body)
        if close_match:
            app_raw = close_match.group(1).strip().lower()
            resolved_app = KNOWN_APP_MAP.get(app_raw, close_match.group(1).strip())
            return RouteDecision(
                tier=ExecutionTier.DIRECT,
                action="control",
                action_payload={"type": "close_app", "app": resolved_app},
                target_device="desktop",
                confidence=1.0,
                reason="Deterministic desktop app close",
                suggested_text=f"Closing {resolved_app}."
            )

        # 7. Open Application
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

        # 8. Mobile notification query
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
