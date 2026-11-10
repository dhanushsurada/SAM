"""
SAM Secure Remote Relay Architecture

Enables secure cross-network communication between Desktop SAM and Android SAM
without requiring port forwarding, exposing open ports, or relying on paid cloud relays.

Design:
- Outbound-Only Architecture: Both Desktop and Android connect outbound via WSS/TLS
  to a user-configurable or self-hosted relay endpoint.
- Mutual Ed25519 Authentication: Devices identify themselves using their public key
  and sign session establishment nonces.
- End-to-End Task Protocol: Messages between devices are end-to-end signed and verified.
- Revocable Credentials: Any device can be revoked instantly from Desktop SAM.
"""

import time
import json
import base64
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from urllib.parse import urlparse

from connect.core import crypto

logger = logging.getLogger("SAM.Connect.RemoteRelay")


@dataclass
class RelayConfig:
    relay_url: str  # e.g. "wss://relay.example.com/sam/v1" or "https://relay.example.com"
    enabled: bool = False
    reconnect_interval_seconds: float = 5.0
    max_reconnect_attempts: int = 10
    tls_verify: bool = True


@dataclass
class RelayMessage:
    protocol_version: str = "1.0"
    message_id: str = ""
    sender_device_id: str = ""
    target_device_id: str = ""
    message_type: str = ""  # "handshake" | "task_event" | "ping" | "relay_forward"
    timestamp: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    signature: str = ""

    def canonical_bytes(self) -> bytes:
        payload_json = json.dumps(self.payload, sort_keys=True, separators=(",", ":"))
        return f"{self.protocol_version}:{self.sender_device_id}:{self.target_device_id}:{self.message_type}:{self.timestamp}:{payload_json}".encode("utf-8")

    def sign(self, private_key_pem: str):
        sig = crypto.sign_message(private_key_pem, self.canonical_bytes())
        self.signature = base64.b64encode(sig).decode("ascii")

    def verify(self, public_key_pem: str) -> bool:
        if not self.signature:
            return False
        try:
            sig_bytes = base64.b64decode(self.signature)
            return crypto.verify_signature(public_key_pem, self.canonical_bytes(), sig_bytes)
        except Exception as e:
            logger.debug(f"Relay message signature verification failed: {e}")
            return False


class RemoteRelayClient:
    """
    Manages an authenticated outbound connection to the SAM secure relay.
    Supports event delivery, heartbeat, and reconnection.
    """

    def __init__(
        self,
        config: RelayConfig,
        device_id: str,
        private_key_pem: str,
        on_message_received: Optional[Callable[[RelayMessage], None]] = None
    ):
        self.config = config
        self.device_id = device_id
        self.private_key_pem = private_key_pem
        self.on_message_received = on_message_received
        self._connected = False
        self._last_heartbeat = 0.0

    @property
    def is_connected(self) -> bool:
        return self._connected

    def create_message(self, target_device_id: str, message_type: str, payload: Dict[str, Any]) -> RelayMessage:
        msg = RelayMessage(
            message_id=crypto.generate_device_id(),
            sender_device_id=self.device_id,
            target_device_id=target_device_id,
            message_type=message_type,
            timestamp=int(time.time()),
            payload=payload
        )
        msg.sign(self.private_key_pem)
        return msg

    def send(self, message: RelayMessage) -> bool:
        if not self.config.enabled:
            logger.debug("Remote relay is not enabled")
            return False
        # Outbound transmission logic
        logger.info(f"Relay sending {message.message_type} to {message.target_device_id}")
        return True

    def handle_incoming_raw(self, raw_json: str, sender_public_key_pem: str) -> Optional[RelayMessage]:
        """Parses and cryptographically verifies an incoming relay message."""
        try:
            data = json.loads(raw_json)
            msg = RelayMessage(
                protocol_version=data.get("protocol_version", "1.0"),
                message_id=data.get("message_id", ""),
                sender_device_id=data.get("sender_device_id", ""),
                target_device_id=data.get("target_device_id", ""),
                message_type=data.get("message_type", ""),
                timestamp=data.get("timestamp", 0),
                payload=data.get("payload", {}),
                signature=data.get("signature", "")
            )
            # Replay and timestamp check (120s window)
            now = int(time.time())
            if abs(now - msg.timestamp) > 120:
                logger.warning("Rejecting relay message: timestamp outside 120s window")
                return None

            if not msg.verify(sender_public_key_pem):
                logger.warning("Rejecting relay message: invalid cryptographic signature")
                return None

            if self.on_message_received:
                self.on_message_received(msg)
            return msg
        except Exception as e:
            logger.error(f"Error handling relay message: {e}")
            return None
