"""
SAM Interfaces — API — Connect Schemas

(New in agent/cross-device.) Request/response models for /api/connect/*,
kept in their own file the same way /api/iqoo/*'s models live in
interfaces/api/schemas.py rather than inline in server.py.

Deliberately thin: connect/core/capabilities.py's validate_capabilities()
and connect/core/device_registry.py's own validation are still the real
gatekeepers (a malformed capabilities map raises CapabilityValidationError
regardless of what shape got past these models) — Capabilities is typed
loosely here (Dict[str, Dict]) rather than re-encoding that whole schema a
second time in Pydantic. See docs/architecture/CROSS_DEVICE_PROTOCOL.md for
the full field-by-field contract.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

Capabilities = Dict[str, Dict[str, Any]]


# ─── Pairing ────────────────────────────────────────────────────────────

class PairingStartResponse(BaseModel):
    v: str = "1.0"  # connect.transports.lan_http.PROTOCOL_VERSION — a string, e.g. "1.0"
    token: str
    host: str
    port: int
    expires_at: str


class PairingRedeemRequest(BaseModel):
    token: str
    device_id: str
    device_name: str = "Phone"
    platform: str
    public_key: str
    capabilities: Capabilities = Field(default_factory=dict)
    protocol_version: Optional[str] = None


class PairingRedeemResponse(BaseModel):
    device_id: str
    status: str = "trusted"


# ─── Devices ────────────────────────────────────────────────────────────

class DeviceRecord(BaseModel):
    id: int
    channel: str
    external_id: str
    device_name: Optional[str] = None
    status: str
    paired_at: Optional[str] = None
    last_active: Optional[str] = None
    platform: Optional[str] = None
    protocol_version: Optional[str] = None
    capabilities: Capabilities = Field(default_factory=dict)
    connection_state: str


class RenameDeviceRequest(BaseModel):
    name: str


class CapabilitiesUpdateRequest(BaseModel):
    capabilities: Capabilities


class HeartbeatResponse(BaseModel):
    device_id: str
    connection_state: str
    pending_tasks: List["DeviceTaskRecord"]


# ─── Device tasks ───────────────────────────────────────────────────────

class DeviceTaskCreateRequest(BaseModel):
    target_device_id: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    required_capability: Optional[str] = None
    idempotency_key: Optional[str] = None
    timeout_seconds: int = 300
    context_ref: Optional[str] = None
    handoff_state: Optional[Dict[str, Any]] = None


class DeviceTaskRecord(BaseModel):
    task_id: str
    origin: str
    target_device_id: str
    action: str
    payload: Dict[str, Any]
    required_capability: Optional[str] = None
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    last_message: Optional[str] = None
    last_pct: Optional[int] = None
    idempotency_key: Optional[str] = None
    context_ref: Optional[str] = None
    handoff_state: Optional[Dict[str, Any]] = None
    handoff_of: Optional[str] = None
    timeout_seconds: int
    created_at: str
    updated_at: str


HeartbeatResponse.model_rebuild()


class TaskProgressRequest(BaseModel):
    message: str
    pct: Optional[int] = None


class TaskActionRequest(BaseModel):
    description: str


class TaskVerificationRequest(BaseModel):
    verified: bool
    detail: str = ""


class TaskCompleteRequest(BaseModel):
    result: Optional[Dict[str, Any]] = None


class TaskFailRequest(BaseModel):
    error: str


class TaskCancelRequest(BaseModel):
    reason: Optional[str] = None


class TaskHandoffRequest(BaseModel):
    new_target_device_id: str
    reason: Optional[str] = None
