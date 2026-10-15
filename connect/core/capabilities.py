"""
SAM Connect — Capability Model

(New in agent/cross-device. Populates a gap the existing device registry
doesn't cover: connect/core/device_registry.py knows WHO a device is and
WHETHER it's trusted, but nothing today records WHAT a trusted device can
actually do. Section 16 of the Master PDR lists "Capability model —
Capability, platform, availability and permission" as one of the shared
integration contracts Agent 3 owns; this module is that contract.)

A device (Android today; any future SAM Connect device tomorrow)
self-reports a capability map at pairing time and may update it later
(e.g. after the user grants/revokes an OS permission). connect/services/
task_handoff.py checks this map before routing a task that requires a
specific capability — "Do not claim capabilities that are unavailable or
denied" (Agent 3 execution prompt, section 5) is enforced here, in one
place, rather than re-implemented at every call site.

This module is intentionally dumb storage/validation, not a permissions
system of its own — SAM Core's own permission model (interfaces/desktop's
Permissions surface, per the PDR's information architecture) remains the
source of truth for OS-level grants; a device is just reporting its own
view of that state.
"""

from typing import Dict

# Canonical capability names. Deliberately a small, closed vocabulary
# (matches the example structure in the Agent 3 execution prompt, section
# 5) rather than a free-form string field — an unrecognized capability
# name is a bug to catch at validation time, not a typo to silently route
# tasks against.
VOICE = "voice"
NOTIFICATIONS = "notifications"
APP_LAUNCH = "app-launch"
CAMERA = "camera"
DEVICE_CONTROL = "device-control"

KNOWN_CAPABILITIES = frozenset({
    VOICE, NOTIFICATIONS, APP_LAUNCH, CAMERA, DEVICE_CONTROL,
})

# A capability's reported state. "not_requested" is distinct from
# "denied" — the first means the app never asked the OS for the
# permission yet, the second means the user said no. Collapsing these
# would make "ask again" and "respect the user's denial" indistinguishable
# at the routing layer.
VALID_PERMISSION_STATES = frozenset({"granted", "denied", "not_requested"})


class CapabilityValidationError(ValueError):
    pass


def validate_capabilities(raw: Dict) -> Dict[str, Dict]:
    """
    Validates and normalizes a device-reported capability map.

    Expected shape (extra/unknown top-level keys are rejected — see
    docs/architecture/CROSS_DEVICE_PROTOCOL.md for the wire format):

        {
          "voice":         {"available": true,  "permission": "granted"},
          "notifications": {"available": true,  "permission": "granted"},
          "app-launch":     {"available": true,  "permission": "not_requested"},
          "camera":        {"available": false, "permission": "not_requested"},
          "device-control": {"available": true,  "permission": "denied"}
        }

    A capability may be entirely omitted (treated as unavailable) — a
    device only needs to report what it actually has. Raises
    CapabilityValidationError on anything malformed; callers should turn
    that into a 422 at the HTTP boundary rather than store a partial map.
    """
    if not isinstance(raw, dict):
        raise CapabilityValidationError("capabilities must be a JSON object")

    unknown = set(raw.keys()) - KNOWN_CAPABILITIES
    if unknown:
        raise CapabilityValidationError(f"unknown capability name(s): {sorted(unknown)}")

    normalized: Dict[str, Dict] = {}
    for name, entry in raw.items():
        if not isinstance(entry, dict):
            raise CapabilityValidationError(f"capability '{name}' must be an object")
        available = entry.get("available", False)
        permission = entry.get("permission", "not_requested")
        if not isinstance(available, bool):
            raise CapabilityValidationError(f"capability '{name}'.available must be a boolean")
        if permission not in VALID_PERMISSION_STATES:
            raise CapabilityValidationError(
                f"capability '{name}'.permission must be one of {sorted(VALID_PERMISSION_STATES)}"
            )
        # A capability that isn't available can't simultaneously be
        # "granted" — that combination would let a task get routed on the
        # strength of a permission for a capability that doesn't exist.
        if not available and permission == "granted":
            permission = "not_requested"
        normalized[name] = {"available": available, "permission": permission}

    return normalized


def device_supports(capabilities: Dict[str, Dict], capability: str) -> bool:
    """
    True only if the device has reported this exact capability as both
    available and permission-granted. Missing/unknown capability, not
    available, or not granted all return False — the caller (task
    routing) should surface *why* separately (see
    connect.services.task_handoff.CapabilityUnavailableError) rather than
    infer it from a bare False.
    """
    entry = capabilities.get(capability)
    if not entry:
        return False
    return bool(entry.get("available")) and entry.get("permission") == "granted"
