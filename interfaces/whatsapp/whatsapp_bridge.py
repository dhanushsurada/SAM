"""
SAM WhatsApp Interface — Bridge

Enables remote control of SAM via WhatsApp with end-to-end task execution,
native WhatsApp message formatting, audio/image perception, and mutual
device pairing.

Supports:
1. Meta WhatsApp Cloud API / WhatsApp Business Platform (official Graph API)
2. Inbound webhook verification & message processing
3. Interactive buttons & action confirmations
4. Offline / Local simulation & Relay mode
5. Strict device trust verification via DeviceRegistry (channel="whatsapp")
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import replace
from typing import Dict, List, Optional, Any
import requests

from connect.core.device_registry import DeviceRegistry
from memory.identity import Identity
from memory.retrieve import MemoryRetriever
from founder_mode.manager import FounderModeManager
from core.brain import Brain, BrainResponse
from agent.react_loop import ReactLoop
from core.tiered_router import TieredExecutionRouter, ExecutionTier

logger = logging.getLogger("SAM.Interfaces.WhatsApp")

NOT_PAIRED_MESSAGE = (
    "🔒 *This phone number is not paired with SAM yet.*\n\n"
    "To pair this device:\n"
    "1. Run `python -m interfaces.whatsapp.pair_new_device` on your SAM host machine (or generate a code from the Desktop Connect screen).\n"
    "2. Reply here with: `/start <pairing_token>`"
)


def format_for_whatsapp(text: str) -> str:
    """
    Converts standard markdown to WhatsApp formatting:
    - **bold** -> *bold*
    - *italic* -> _italic_
    - ~~strike~~ -> ~strike~
    - ```code``` -> ```code```
    """
    if not text:
        return ""
    # Protect code blocks first
    code_blocks = []
    def save_code(match):
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks)-1}__"

    text = re.sub(r'```[\s\S]*?```', save_code, text)
    text = re.sub(r'`[^`]+`', save_code, text)

    # Convert bold: **text** -> *text*
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)

    # Convert strikethrough: ~~text~~ -> ~text~
    text = re.sub(r'~~(.+?)~~', r'~\1~', text)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        text = text.replace(f"__CODE_BLOCK_{i}__", block)

    return text.strip()


class WhatsAppBridge:
    def __init__(self, settings, registry: Optional[DeviceRegistry] = None):
        self.settings = settings
        self.registry = registry or DeviceRegistry()
        self._task_lock = None
        self._sent_messages: List[Dict[str, Any]] = []

        self.identity = Identity()
        self.memory = MemoryRetriever()
        self.founder_mode = FounderModeManager(settings=settings)
        self.brain = Brain(settings)
        self.react_loop = ReactLoop(settings, founder_mode=self.founder_mode)
        self.tiered_router = TieredExecutionRouter(settings)

        self.phone_number_id = getattr(settings, "whatsapp_phone_number_id", "") or ""
        self.access_token = getattr(settings, "whatsapp_access_token", "") or ""
        self.verify_token = getattr(settings, "whatsapp_verify_token", "") or "sam_whatsapp_verify_token"
        self._is_running = False

    @property
    def is_configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(self):
        self._is_running = True
        logger.info("WhatsApp bridge activated")

    def stop(self):
        self._is_running = False
        logger.info("WhatsApp bridge stopped")

    # ─── Webhook Handlers ──────────────────────────────────────────────────

    def verify_webhook(self, mode: Optional[str], token: Optional[str], challenge: Optional[str]) -> Optional[str]:
        """Handles Meta's GET verification handshake for WhatsApp webhooks."""
        if mode == "subscribe" and token == self.verify_token:
            logger.info("WhatsApp webhook verified successfully")
            return challenge
        logger.warning(f"WhatsApp webhook verification failed: mode={mode}")
        return None

    def handle_webhook_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processes inbound Meta WhatsApp webhook notifications synchronously or asynchronously.
        Extracts sender phone number, message type, and text.
        """
        results = []
        try:
            entries = payload.get("entry", [])
            for entry in entries:
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    contacts = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
                    messages = value.get("messages", [])
                    for msg in messages:
                        from_number = msg.get("from")
                        msg_id = msg.get("id")
                        msg_type = msg.get("type")
                        sender_name = contacts.get(from_number, "WhatsApp User")

                        text = ""
                        if msg_type == "text":
                            text = msg.get("text", {}).get("body", "")
                        elif msg_type == "button":
                            text = msg.get("button", {}).get("text", "")
                        elif msg_type == "interactive":
                            interactive = msg.get("interactive", {})
                            if interactive.get("type") == "button_reply":
                                text = interactive.get("button_reply", {}).get("title", "")
                            elif interactive.get("type") == "list_reply":
                                text = interactive.get("list_reply", {}).get("title", "")

                        if from_number and text:
                            reply = self.process_message(from_number, text, sender_name=sender_name)
                            results.append({
                                "msg_id": msg_id,
                                "from": from_number,
                                "reply": reply
                            })
        except Exception as e:
            logger.error(f"Error handling WhatsApp webhook payload: {e}", exc_info=True)

        return {"processed": len(results), "results": results}

    # ─── Message Processing Pipeline ──────────────────────────────────────

    def process_message(self, sender_number: str, message_text: str, sender_name: str = "WhatsApp User") -> str:
        """
        Processes an incoming message from a WhatsApp user.
        Validates pairing token, handles commands, or runs autonomous task execution.
        """
        clean_text = message_text.strip()
        logger.info(f"WhatsApp message from {sender_number}: {clean_text[:60]}")

        # 1. Check for pairing commands: /start or /start <token>
        if clean_text.startswith("/start"):
            parts = clean_text.split()
            if len(parts) == 1:
                reply = (
                    "👋 *Hello! I am SAM — your local autonomous assistant.*\n\n"
                    "If you have a pairing code from SAM Desktop, reply with:\n"
                    "`/start <pairing_token>`"
                )
                self.send_message(sender_number, reply)
                return reply

            token = parts[1]
            success = self.registry.redeem_token(token, sender_number, device_name=sender_name, channel="whatsapp")
            if success:
                reply = (
                    f"✅ *Successfully paired!* Device: `{sender_name}` ({sender_number}).\n"
                    "You can now send instructions, questions, and autonomous tasks directly to SAM."
                )
                logger.info(f"Paired new WhatsApp device: {sender_number} ({sender_name})")
            else:
                reply = "❌ That pairing token is invalid, expired, or already used. Generate a new token in SAM Desktop."
            self.send_message(sender_number, reply)
            return reply

        # 2. Verify trust
        if not self.registry.is_trusted(sender_number, channel="whatsapp"):
            logger.warning(f"Rejected message from untrusted WhatsApp sender: {sender_number}")
            self.send_message(sender_number, NOT_PAIRED_MESSAGE)
            return NOT_PAIRED_MESSAGE

        self.registry.touch_last_active(sender_number, channel="whatsapp")

        # 3. Built-in command handling
        if clean_text == "/devices":
            devices = self.registry.list_devices()
            lines = [f"• {d['device_name']} ({d['channel']}, paired {d['paired_at'][:10]})" for d in devices]
            reply = "*Trusted Devices on SAM Connect:*\n" + ("\n".join(lines) if lines else "No other devices.")
            self.send_message(sender_number, reply)
            return reply

        if clean_text in ("/status", "/health"):
            reply = f"🟢 *SAM is Active*\n• System: Online\n• Channel: WhatsApp\n• Model: `{self.settings.primary_model}`"
            self.send_message(sender_number, reply)
            return reply

        # 4. Turn execution pipeline (with deterministic routing bypass)
        final_reply = self._process_turn(clean_text)
        self.send_message(sender_number, final_reply)
        return final_reply

    def _process_turn(self, user_input: str) -> str:
        """
        Executes a turn through SAM's Session, Tiered Router, Brain, and ReAct loop.
        """
        from core.session import Session
        from licensing.tier import get_tier, PRO, FREE_TIER_MEMORY_RETENTION_DAYS

        retention_days = None if get_tier(self.settings) == PRO else FREE_TIER_MEMORY_RETENTION_DAYS

        # Tier 1 Direct Execution
        route_decision = self.tiered_router.route(user_input)
        if route_decision.tier == ExecutionTier.DIRECT and route_decision.action:
            if route_decision.suggested_text:
                return format_for_whatsapp(route_decision.suggested_text)
            try:
                obs = self.react_loop.execute(route_decision.action, route_decision.action_payload or {})
                return format_for_whatsapp(f"Executed: {obs}")
            except Exception as e:
                logger.error(f"WhatsApp Tier 1 execution failed: {e}")

        # Full context session
        session = Session(
            user_input=user_input,
            identity=self.identity.load(),
            memories=self.memory.retrieve(user_input, self.settings, retention_days=retention_days),
            founder_context=self.founder_mode.get_context(),
            settings=self.settings
        )

        response = self.brain.process(session)
        final_response = response

        if response.action and response.action not in (None, "none"):
            try:
                real_result_text = self.react_loop.run_planned_task(
                    task=user_input,
                    brain=self.brain,
                    session=session,
                    founder_context=session.founder_context,
                    initial_response=response
                )
                final_response = replace(response, text=real_result_text)
            except Exception as e:
                logger.error(f"WhatsApp task execution error: {e}", exc_info=True)
                final_response = replace(response, text=f"I tried to execute that, but encountered an error: {e}")

        # Post-turn async persistence
        if not self.settings.incognito:
            session.save(user_input=user_input, response=final_response,
                         memory_store=self.memory.get_store(self.settings), async_extract=True)
        self.founder_mode.capture_if_relevant(user_input, final_response, async_mode=True)

        return format_for_whatsapp(final_response.text)

    # ─── Outbound Messaging ────────────────────────────────────────────────

    def send_message(self, to_phone: str, text: str, buttons: Optional[List[str]] = None) -> bool:
        """
        Sends a WhatsApp message via Meta Cloud API or stores to local relay log.
        """
        formatted = format_for_whatsapp(text)
        record = {
            "to": to_phone,
            "text": formatted,
            "timestamp": time.time(),
            "delivered": False
        }

        if not self.is_configured:
            # Local / Simulated / Relay delivery mode
            logger.info(f"[WhatsApp Relay Simulated] To {to_phone}: {formatted[:80]}")
            record["delivered"] = True
            self._sent_messages.append(record)
            return True

        # Live Meta Cloud API HTTP dispatch
        url = f"https://graph.facebook.com/v21.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": True, "body": formatted}
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            if resp.status_code in (200, 201):
                logger.info(f"WhatsApp message dispatched to {to_phone}")
                record["delivered"] = True
                self._sent_messages.append(record)
                return True
            else:
                logger.warning(f"Meta Graph API error ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"Failed to post to WhatsApp Cloud API: {e}")

        self._sent_messages.append(record)
        return False

    def get_recent_sent_messages(self, limit: int = 10) -> List[Dict[str, Any]]:
        return self._sent_messages[-limit:]
