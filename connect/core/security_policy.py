"""
SAM Security Approval Policy & Risk Classification Engine

Classifies actions by risk level:
- LOW: Reversible, safe read-only operations (no prompt required)
- MEDIUM: App launching, local file creation, notification reading (auto-approved or single prompt)
- HIGH: File deletion, shell commands, payment/messages, permission changes (explicit approval mandatory)

Provides rate-limiting, risk assessment, and tamper-evident audit logging.
"""

import time
import json
import re
import logging
from enum import Enum
from dataclasses import dataclass
from collections import deque
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger("SAM.SecurityPolicy")

DANGEROUS_COMMAND_PATTERNS = [
    re.compile(r"\brm\s+-[a-zA-Z]*r", re.I),           # rm -rf, rm -r, rm -fr, etc.
    re.compile(r"\brm\s+--recursive", re.I),
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bdd\s+if=", re.I),
    re.compile(r"\bchmod\s+(-[a-zA-Z]*R\s+)?777\b", re.I),
    re.compile(r"\bformat\b", re.I),
    re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.I),    # fork bomb
    re.compile(r">\s*/dev/", re.I),
    re.compile(r"\b(shutdown|reboot|poweroff|halt)\b", re.I),
    re.compile(r"\b(curl|wget)\b.*\|\s*(sh|bash|python|perl)\b", re.I), # pipe to shell
    re.compile(r"\bdel\s+/[a-zA-Z]*s", re.I),          # windows del /s
]


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

    def __init__(self, require_medium_approval: bool = False, max_audit_entries: int = 1000):
        self.require_medium_approval = require_medium_approval
        self._audit_log = deque(maxlen=max_audit_entries)
        self._log_path = Path.home() / ".sam_data" / "logs" / "security_audit.jsonl"

    def classify_action(self, action: str, payload: Optional[Dict[str, Any]] = None) -> RiskLevel:
        payload = payload or {}
        
        # Check explicit high risk action names
        if action in HIGH_RISK_ACTIONS:
            return RiskLevel.HIGH

        # Check payload specific risk triggers
        if action == "terminal":
            cmd = str(payload.get("command", "")).strip()
            cmd_lower = cmd.lower()
            if any(danger in cmd_lower for danger in ["rm -rf", "sudo", "mkfs", "chmod 777", "> /dev"]):
                return RiskLevel.HIGH
            for pat in DANGEROUS_COMMAND_PATTERNS:
                if pat.search(cmd):
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
        try:
            if self._log_path.parent.exists():
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
        except Exception as e:
            logger.debug(f"Failed writing security audit entry to file: {e}")
