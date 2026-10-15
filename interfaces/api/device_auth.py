"""
SAM Interfaces — API — Device Authentication Dependency

(New in agent/cross-device. This is the file connect/transports/lan_http.py's
module docstring calls "the only intended caller" of verify_request().)

connect/transports/lan_http.py deliberately has no FastAPI import anywhere in
it — it's framework-agnostic on purpose (see its own docstring). This module
is the thin FastAPI-shaped wrapper around it: pull the four X-SAM-* headers
and the raw body off a Request, call verify_request(), turn a DeviceAuthError
into a 401. Nothing here re-implements any verification logic.

It also owns the process-lifetime singletons every /api/connect/* route
needs (DeviceRegistry, ConnectEventBus, NonceCache, DeviceTaskRouter) —
same lazy-singleton-behind-a-getter pattern as interfaces/api/server.py's
get_gateway(), so there's exactly one of each per running server, not one
per request. interfaces/api/connect_routes.py imports these getters rather
than constructing its own copies.

=== device.connected ===
connect/core/events.py's ConnectEventBus exists, but nothing in
connect/transports/lan_http.py or connect/services/task_handoff.py ever
calls .publish() with a device.* event — by design, neither of those
modules has (or should have) an event-bus dependency of its own (see their
docstrings). This dependency is where that gets wired up: it reads the
device's connection_state *before* calling verify_request() (which records
the heartbeat as a side effect and would otherwise erase the "before"
state), and publishes device.connected exactly on an offline/unknown ->
online transition — not on every single authenticated request, which would
flood the "device" stream on every heartbeat from an already-online phone.
"""

import logging

from fastapi import Header, HTTPException, Request

from connect.core.device_registry import DIRECT_CHANNEL, DeviceRegistry
from connect.core.events import ConnectEventBus
from connect.services.task_handoff import DeviceTaskRouter
from connect.transports import lan_http
from connect.transports.lan_http import DeviceAuthError, NonceCache

logger = logging.getLogger("SAM.API.DeviceAuth")

_registry: DeviceRegistry = None
_event_bus: ConnectEventBus = None
_nonce_cache: NonceCache = None
_task_router: DeviceTaskRouter = None


def get_registry() -> DeviceRegistry:
    global _registry
    if _registry is None:
        _registry = DeviceRegistry()
    return _registry


def get_event_bus() -> ConnectEventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = ConnectEventBus()
    return _event_bus


def get_nonce_cache() -> NonceCache:
    global _nonce_cache
    if _nonce_cache is None:
        _nonce_cache = NonceCache()
    return _nonce_cache


def get_task_router() -> DeviceTaskRouter:
    global _task_router
    if _task_router is None:
        _task_router = DeviceTaskRouter(get_registry(), get_event_bus())
    return _task_router


def reset_singletons_for_tests():
    """Test-only. Offline test suites construct many short-lived registries
    against different HOME dirs (same convention as interfaces/api/gateway.py's
    tests) — this drops the module-level singletons so the next get_*() call
    rebuilds against whatever HOME is current, instead of silently reusing a
    DeviceRegistry pointed at a previous test's directory."""
    global _registry, _event_bus, _nonce_cache, _task_router
    _registry = None
    _event_bus = None
    _nonce_cache = None
    _task_router = None


async def require_trusted_device(
    request: Request,
    x_sam_device_id: str = Header(default=None, alias="X-SAM-Device-Id"),
    x_sam_timestamp: str = Header(default=None, alias="X-SAM-Timestamp"),
    x_sam_nonce: str = Header(default=None, alias="X-SAM-Nonce"),
    x_sam_signature: str = Header(default=None, alias="X-SAM-Signature"),
) -> dict:
    """FastAPI dependency (`Depends(require_trusted_device)`): verifies a
    signed request from a "direct" (LAN-paired) device and returns its
    device dict (same shape as DeviceRegistry.get_device_by_external_id).
    Raises HTTPException(401) — with lan_http's own specific message — on
    anything from a missing header to an outright forged signature; every
    /api/connect/* route that a *device* calls (as opposed to one the
    desktop/Core calls about a device) depends on this.
    """
    registry = get_registry()
    body = await request.body()

    prior = (
        registry.get_device_by_external_id(x_sam_device_id, channel=DIRECT_CHANNEL)
        if x_sam_device_id
        else None
    )
    was_online = bool(prior) and prior.get("connection_state") == "online"

    try:
        device = lan_http.verify_request(
            registry,
            get_nonce_cache(),
            method=request.method,
            path=request.url.path,
            body=body,
            device_id=x_sam_device_id,
            timestamp=x_sam_timestamp,
            nonce=x_sam_nonce,
            signature_b64=x_sam_signature,
        )
    except DeviceAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e

    if not was_online:
        get_event_bus().publish_to(
            [f"device:{device['external_id']}", "device"],
            "device.connected",
            device_id=device["external_id"],
            device_name=device.get("device_name"),
            platform=device.get("platform"),
        )
        logger.info(f"device.connected: {device['external_id']} ({device.get('device_name')})")

    return device
