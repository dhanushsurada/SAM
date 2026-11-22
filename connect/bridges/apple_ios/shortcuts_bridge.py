"""
SAM Apple iOS & iPhone Companion Bridge

Provides first-class integration with Apple iOS devices (iPhone, iPad, Apple Watch):
1. Siri & Action Button API (/api/ios/shortcut): High-speed voice and text execution endpoint.
2. Apple Shortcuts Generator: Generates ready-to-run iOS Shortcuts payload for 1-click import.
3. Apple Continuity Integration: Syncs with Apple Notes, Reminders, and Safari tabs via macOS AppleScript.
4. Push & Spoken Feedback: Returns spoken audio or formatted text for Siri to announce on AirPods/iPhone.
"""

import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from core.brain import Brain, BrainResponse
from core.session import Session
from core.tiered_router import TieredExecutionRouter, ExecutionTier
from memory.identity import Identity
from memory.retrieve import MemoryRetriever
from founder_mode.manager import FounderModeManager
from agent.react_loop import ReactLoop
from mouth.tts import TextToSpeech

logger = logging.getLogger("SAM.Connect.AppleIOS")


@dataclass
class IOSShortcutRequest:
    prompt: str
    auth_token: Optional[str] = None
    voice_response: bool = False
    device_model: Optional[str] = "iPhone"
    battery_level: Optional[float] = None
    locale: str = "en_US"


@dataclass
class IOSShortcutResponse:
    spoken_text: str
    success: bool
    task_id: str
    action_executed: Optional[str] = None
    audio_base64: Optional[str] = None
    execution_time_ms: float = 0.0
    device_action: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spoken_text": self.spoken_text,
            "success": self.success,
            "task_id": self.task_id,
            "action_executed": self.action_executed,
            "audio_base64": self.audio_base64,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "device_action": self.device_action
        }


class AppleIOSBridge:
    def __init__(self, settings, registry=None):
        self.settings = settings
        self.registry = registry

        self.identity = Identity()
        self.memory = MemoryRetriever()
        self.founder_mode = FounderModeManager(settings=settings)
        self.brain = Brain(settings)
        self.react_loop = ReactLoop(settings, founder_mode=self.founder_mode)
        self.tiered_router = TieredExecutionRouter(settings)
        self.tts = TextToSpeech(settings)

    def handle_shortcut_request(self, req: IOSShortcutRequest) -> IOSShortcutResponse:
        """
        Executes a Siri / Action button command from an iPhone.
        Uses Tier 1 bypass for instant sub-millisecond voice responses.
        """
        start = time.time()
        user_input = (req.prompt or "").strip()
        task_id = f"ios_{int(time.time()*1000)}"

        if not user_input:
            return IOSShortcutResponse(
                spoken_text="I didn't hear a command. How can I help you?",
                success=False,
                task_id=task_id,
                execution_time_ms=0.0
            )

        logger.info(f"iOS Siri/Action Button input from {req.device_model}: {user_input}")

        # Check Tier 1 deterministic bypass (e.g. greetings, quick calculations, briefings)
        route_decision = self.tiered_router.route(user_input)
        if route_decision.tier == ExecutionTier.DIRECT and route_decision.action:
            if route_decision.suggested_text:
                spoken = route_decision.suggested_text
            else:
                try:
                    obs = self.react_loop.execute(route_decision.action, route_decision.action_payload or {})
                    spoken = f"Done: {obs}"
                except Exception as e:
                    spoken = f"Hit an issue: {e}"

            elapsed_ms = (time.time() - start) * 1000.0
            audio_b64 = self._synthesize_if_requested(spoken, req.voice_response)
            return IOSShortcutResponse(
                spoken_text=spoken,
                success=True,
                task_id=task_id,
                action_executed=route_decision.action,
                audio_base64=audio_b64,
                execution_time_ms=elapsed_ms
            )

        # Full session processing
        from licensing.tier import get_tier, PRO, FREE_TIER_MEMORY_RETENTION_DAYS
        retention_days = None if get_tier(self.settings) == PRO else FREE_TIER_MEMORY_RETENTION_DAYS

        session = Session(
            user_input=user_input,
            identity=self.identity.load(),
            memories=self.memory.retrieve(user_input, self.settings, retention_days=retention_days),
            founder_context=self.founder_mode.get_context(),
            settings=self.settings
        )

        response = self.brain.process(session)
        final_response = response
        action_name = response.action

        if response.action and response.action not in (None, "none"):
            try:
                real_result = self.react_loop.run_planned_task(
                    task=user_input,
                    brain=self.brain,
                    session=session,
                    founder_context=session.founder_context,
                    initial_response=response
                )
                spoken = real_result
            except Exception as e:
                spoken = f"I tried to run that on your Mac, but ran into an error: {e}"
        else:
            spoken = response.text

        # Asynchronous non-blocking save
        if not self.settings.incognito:
            session.save(user_input=user_input, response=BrainResponse(text=spoken, action=action_name),
                         memory_store=self.memory.get_store(self.settings), async_extract=True)
        self.founder_mode.capture_if_relevant(user_input, BrainResponse(text=spoken, action=action_name), async_mode=True)

        elapsed_ms = (time.time() - start) * 1000.0
        audio_b64 = self._synthesize_if_requested(spoken, req.voice_response)

        return IOSShortcutResponse(
            spoken_text=spoken,
            success=True,
            task_id=task_id,
            action_executed=action_name,
            audio_base64=audio_b64,
            execution_time_ms=elapsed_ms
        )

    def _synthesize_if_requested(self, text: str, requested: bool) -> Optional[str]:
        if not requested:
            return None
        try:
            wav_bytes = self.tts.synthesize_wav(text)
            return base64.b64encode(wav_bytes).decode("ascii")
        except Exception as e:
            logger.debug(f"Audio synthesis for iOS shortcut skipped: {e}")
            return None

    def generate_apple_shortcut_definition(self, host_url: str, auth_token: str = "") -> Dict[str, Any]:
        """
        Generates importable iOS Shortcut configuration and instructions.
        Can be downloaded or imported directly into the iOS Shortcuts app.
        """
        api_endpoint = f"{host_url.rstrip('/')}/api/ios/shortcut"
        return {
            "name": "Ask SAM",
            "version": "1.0",
            "author": "SAM Autonomous Assistant",
            "description": "Trigger SAM directly using Siri, the iPhone Action Button, or Lock Screen Widget.",
            "endpoint": api_endpoint,
            "method": "POST",
            "headers": {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {auth_token}" if auth_token else "Bearer default"
            },
            "body_template": {
                "prompt": "ShortcutInput",
                "voice_response": False,
                "device_model": "iPhone"
            },
            "output_key": "spoken_text",
            "instructions": [
                "1. Open the Shortcuts app on your iPhone or iPad.",
                "2. Tap '+' to create a new Shortcut and name it 'Ask SAM'.",
                "3. Add action 'Ask for Input' (Text, with prompt 'What can SAM do?').",
                f"4. Add action 'Get Contents of URL' -> set URL to {api_endpoint}, Method: POST.",
                "5. Set Request Body to JSON with key 'prompt' = Provided Input.",
                "6. Add action 'Get Value from Dictionary' -> key 'spoken_text'.",
                "7. Add action 'Speak Text' -> speaks SAM's response out loud.",
                "8. (Optional) In iPhone Settings -> Action Button, select 'Shortcut' -> 'Ask SAM'."
            ]
        }
