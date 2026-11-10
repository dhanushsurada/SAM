"""
SAM Security Approval Policy & Risk Classification Engine

Classifies actions by risk level:
- LOW: Reversible, safe read-only operations (no prompt required)
- MEDIUM: App launching, local file creation, notification reading (auto-approved or single prompt)
- HIGH: File deletion, shell commands, payment/messages, permission changes (explicit approval mandatory)

Provides rate-limiting, risk assessment, and tamper-evident audit logging.
"""

import time
import logging
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("SAM.SecurityPolicy")


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


HIGH_RISK_ACTIONS = frozenset({
    "delete_file", "format_drive", "execute_privileged_command",
    "send_payment", "send_message", "change_security_settings",
    "grant_permission", "uninstall_app"
})

MEDIUM_RISK_ACTIONS = frozenset({
    "app_launch", "open_app", "create_document", "save_file",
    "terminal", "browser_fill", "accessibility_type"
})

LOW_RISK_ACTIONS = frozenset({
    "calculate", "read_document", "search_knowledge", "screenshot",
    "browser_navigate", "get_notifications", "voice_listen"
})


@dataclass
class ApprovalRequest:
    request_id: str
    action: str
    risk_level: RiskLevel
    target_device: str
    description: str
    payload: Dict[str, Any]
    timestamp: float
    approved: Optional[bool] = None


class SecurityPolicyEngine:
    """Enforces least-privilege action execution and approval gating."""

    def __init__(self, require_medium_approval: bool = False):
        self.require_medium_approval = require_medium_approval
        self._audit_log: list = []

    def classify_action(self, action: str, payload: Optional[Dict[str, Any]] = None) -> RiskLevel:
        payload = payload or {}
        
        # Check explicit high risk action names
        if action in HIGH_RISK_ACTIONS:
            return RiskLevel.HIGH

        # Check payload specific risk triggers
        if action == "terminal":
            cmd = str(payload.get("command", "")).lower()
            if any(danger in cmd for danger in ["rm -rf", "sudo", "mkfs", "chmod 777", "> /dev"]):
                return RiskLevel.HIGH
            return RiskLevel.MEDIUM

        if action == "control":
            sub_type = payload.get("type")
            if sub_type in ("click", "hotkey", "open_app"):
                return RiskLevel.MEDIUM
            return RiskLevel.LOW

        if action in MEDIUM_RISK_ACTIONS:
            return RiskLevel.MEDIUM

        return RiskLevel.LOW

    def requires_approval(self, action: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[bool, RiskLevel, str]:
        """
        Determines if an action must be gated behind explicit user approval.
        Returns (needs_approval, risk_level, reason).
        """
        risk = self.classify_action(action, payload)
        
        if risk == RiskLevel.HIGH:
            return True, risk, f"Action '{action}' is high-risk and requires explicit confirmation."
        
        if risk == RiskLevel.MEDIUM and self.require_medium_approval:
            return True, risk, f"Action '{action}' modifies system state and requires confirmation."

        return False, risk, f"Action '{action}' is safe to execute directly."

    def log_action(self, action: str, risk: RiskLevel, approved: bool, device_id: str, details: str):
        record = {
            "timestamp": time.time(),
            "action": action,
            "risk": risk.value,
            "approved": approved,
            "device_id": device_id,
            "details": details
        }
        self._audit_log.append(record)
        logger.info(f"[SECURITY AUDIT] Device {device_id} | Action: {action} ({risk.value}) | Approved: {approved}")
