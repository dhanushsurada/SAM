"""
SAM Interfaces — API — Connect Routes

(New in agent/cross-device.) The FastAPI wiring for everything connect/core,
connect/transports/lan_http.py and connect/services/task_handoff.py
implement but never plug into an actual HTTP server themselves — none of
those three modules import FastAPI, deliberately (see each one's own
docstring: they're framework-agnostic on purpose, so they can be unit
tested without a running server). This file, plus interfaces/api/
device_auth.py, is that wiring.

Mounted into interfaces/api/server.py's existing `app` via
`app.include_router(router)` — server.py's own diff for this whole branch
is three lines (an import, the include_router call, and calling
start_background_tasks()/stop_background_tasks() from its existing
startup/shutdown hooks). The /api/iqoo/* routes server.py already serves
are completely untouched — this is a pure addition, not a modification of
the existing phone-task gateway (see docs/architecture/CROSS_DEVICE_PROTOCOL.md's
"Relationship to /api/iqoo/*" section for why that gateway was deliberately
left alone in this phase, rather than folded into device auth too).

See docs/architecture/CROSS_DEVICE_PROTOCOL.md for the full endpoint-by-
endpoint contract: auth requirements, status codes, and a worked pairing
example.
"""

import asyncio
import ipaddress
import json
import logging
import threading
from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from config.settings import Settings
from connect.core.capabilities import CapabilityValidationError
from connect.core.device_registry import DIRECT_CHANNEL
from connect.core.events import TERMINAL_TASK_EVENT_TYPES
from connect.services.task_handoff import (
    CapabilityUnavailableError,
    InvalidTaskStateError,
    TaskNotFoundError,
    TaskNotOwnedByDeviceError,
    TaskRoutingError,
    UnknownDeviceError,
)
from connect.transports import lan_http
from connect.transports.lan_http import DeviceAuthError

from interfaces.api.connect_schemas import (
    CapabilitiesUpdateRequest,
    DeviceRecord,
    DeviceTaskCreateRequest,
    DeviceTaskRecord,
    HeartbeatResponse,
    PairingRedeemRequest,
    PairingRedeemResponse,
    PairingStartResponse,
    RenameDeviceRequest,
    TaskActionRequest,
    TaskCancelRequest,
    TaskCompleteRequest,
    TaskFailRequest,
    TaskHandoffRequest,
    TaskProgressRequest,
    TaskVerificationRequest,
)
from interfaces.api.device_auth import (
    get_event_bus,
    get_registry,
    get_task_router,
    require_trusted_device,
)

logger = logging.getLogger("SAM.API.Connect")

router = APIRouter(prefix="/api/connect", tags=["connect"])

# How often the background sweep checks for stale-heartbeat devices and
# timed-out device tasks. Well below device_registry.HEARTBEAT_STALE_SECONDS
# (90s) so a disconnect is never more than this much late to appear on the
# "device" event stream.
SWEEP_INTERVAL_SECONDS = 30

_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Lazy singleton so /pairing/start doesn't re-run Settings'
    hardware-detection subprocess call on every single request."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _raise_for_task_error(e: TaskRoutingError):
    """Maps every connect.services.task_handoff.TaskRoutingError subclass
    to the HTTP status docs/architecture/CROSS_DEVICE_PROTOCOL.md documents
    for it. Always raises — never returns — so every call site can rely on
    control flow stopping here."""
    if isinstance(e, UnknownDeviceError):
        raise HTTPException(status_code=404, detail=f"unknown or untrusted device: {e}") from e
    if isinstance(e, CapabilityUnavailableError):
        raise HTTPException(status_code=422, detail=str(e)) from e
    if isinstance(e, TaskNotFoundError):
        raise HTTPException(status_code=404, detail=f"task not found: {e}") from e
    if isinstance(e, TaskNotOwnedByDeviceError):
        raise HTTPException(status_code=403, detail=str(e)) from e
    if isinstance(e, InvalidTaskStateError):
        raise HTTPException(status_code=409, detail=str(e)) from e
    raise HTTPException(status_code=500, detail=str(e)) from e  # pragma: no cover — exhaustive above


def _device_row(internal_id: int) -> Optional[dict]:
    """revoke()/rename() are keyed by the internal int id (see
    connect/core/device_registry.py's own comment on why) and don't return
    the row — this looks it up so the device.updated event below can carry
    the external_id every stream subscriber actually keys off."""
    for d in get_registry().list_devices(include_pending=True):
        if d["id"] == internal_id:
            return d
    return None


# ─── Local-caller restriction (desktop/Core-only endpoints) ──────────────

def _is_loopback_host(host: Optional[str]) -> bool:
    """Robust loopback check via ipaddress.is_loopback rather than a
    hardcoded string set — a naive {"127.0.0.1", "::1"} allowlist (this
    function's first version) silently rejects two real cases: any other
    address in 127.0.0.0/8 (RFC 3330 — all of it is loopback, not just
    .1), and an IPv4-mapped IPv6 address like "::ffff:127.0.0.1", which
    dual-stack sockets can legitimately present for a same-machine
    connection and whose OWN .is_loopback is False (RFC 4291 only defines
    ::1 as the IPv6 loopback address) even though the IPv4 address it
    carries plainly is one — confirmed empirically before writing this,
    not assumed. host=None (no client, e.g. some ASGI test harnesses with
    no real socket) and unparseable strings (Starlette's TestClient
    defaults to the literal "testclient") both fail closed as not
    loopback, matching this function's original behavior for those cases.
    """
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    mapped = getattr(addr, "ipv4_mapped", None)
    return mapped is not None and mapped.is_loopback


def require_local_caller(request: Request) -> None:
    """Dependency for the endpoints this file's own docstrings already
    call "desktop/Core-initiated" by design (pairing/start, device
    management, task create/cancel/handoff) — added on a second pass over
    this branch specifically to close a gap the first pass had only
    documented rather than enforced (see docs/architecture/
    CROSS_DEVICE_PROTOCOL.md §12, "no separate desktop-operator
    authentication"): nothing previously stopped any device on the same
    WiFi from calling them too.

    Safe to add with zero risk to the real desktop client: interfaces/
    desktop/src/api/client.ts's BASE is a same-origin relative path
    ("/api/iqoo", "/api") — a plain `fetch()` against it always resolves
    to whatever origin served the desktop app's own page, which is this
    same FastAPI process (see interfaces/api/server.py's static mount),
    so a legitimate desktop-app request only ever arrives here via the
    loopback interface regardless of proxying. A phone on the LAN, by
    contrast, connects to the server's real LAN IP — never loopback — so
    this rejects exactly the callers it's meant to.

    Every genuinely device-facing endpoint (§4/§6 of the protocol doc —
    pairing/redeem, capabilities, heartbeat, and every task-lifecycle
    call a device itself makes) does NOT use this dependency and is
    reachable over the LAN as designed; only the desktop-only actions
    are restricted here.
    """
    host = request.client.host if request.client else None
    if not _is_loopback_host(host):
        raise HTTPException(
            status_code=403,
            detail="this endpoint is only callable from the local machine running SAM",
        )


# ─── Background sweep (offline detection + task timeouts) ────────────────

_sweep_thread: Optional[threading.Thread] = None
_sweep_stop = threading.Event()


def _sweep_once():
    registry = get_registry()
    events = get_event_bus()
    for device in registry.sweep_offline():
        events.publish_to(
            [f"device:{device['external_id']}", "device"],
            "device.disconnected",
            device_id=device["external_id"],
            device_name=device.get("device_name"),
        )
        logger.info(f"device.disconnected: {device['external_id']} (no heartbeat)")
    for task in get_task_router().sweep_timeouts():
        logger.info(f"device task timed out: {task.task_id} ({task.action} -> {task.target_device_id})")


def _sweep_loop():
    while not _sweep_stop.is_set():
        try:
            _sweep_once()
        except Exception:
            logger.exception("SAM Connect background sweep failed")
        _sweep_stop.wait(SWEEP_INTERVAL_SECONDS)


def start_background_tasks():
    """Called from interfaces/api/server.py's existing @app.on_event("startup").
    Runs connect/core/device_registry.py's sweep_offline() and connect/
    services/task_handoff.py's sweep_timeouts() on a timer — see connect/
    transports/__init__.py's docstring for why this lives here rather than
    inside lan_http.py itself (framework-agnostic modules don't own
    threads; the FastAPI integration layer does)."""
    global _sweep_thread
    _sweep_stop.clear()
    _sweep_thread = threading.Thread(target=_sweep_loop, name="sam-connect-sweep", daemon=True)
    _sweep_thread.start()
    logger.info(f"SAM Connect background sweep started (every {SWEEP_INTERVAL_SECONDS}s)")


def stop_background_tasks():
    """Called from interfaces/api/server.py's existing @app.on_event("shutdown")."""
    _sweep_stop.set()
    if _sweep_thread is not None:
        _sweep_thread.join(timeout=2)
    logger.info("SAM Connect background sweep stopped")


# ─── Pairing ───────────────────────────────────────────────────────────

@router.post("/pairing/start", response_model=PairingStartResponse,
             dependencies=[Depends(require_local_caller)])
def start_pairing():
    """Desktop-only in intent (the QR this returns is meant to be shown on
    the trusted screen, not handed to just any caller) but not
    desktop-authenticated in this phase — matches every existing
    /api/iqoo/* route, none of which require auth either. See
    docs/architecture/CROSS_DEVICE_PROTOCOL.md's Known Limitations."""
    return lan_http.build_pairing_qr_payload(get_registry(), port=get_settings().api_port)


@router.post("/pairing/redeem", response_model=PairingRedeemResponse, status_code=201)
def redeem_pairing(req: PairingRedeemRequest):
    try:
        result = lan_http.redeem_pairing(get_registry(), req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except DeviceAuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    get_event_bus().publish_to(
        [f"device:{req.device_id}", "device"],
        "device.updated",
        device_id=req.device_id, device_name=req.device_name, reason="paired",
    )
    logger.info(f"Device paired via direct/LAN: {req.device_id} ({req.device_name})")
    return result


# ─── Devices ───────────────────────────────────────────────────────────

@router.get("/devices", response_model=List[DeviceRecord],
            dependencies=[Depends(require_local_caller)])
def list_devices(include_pending: bool = False):
    return get_registry().list_devices(include_pending=include_pending)


@router.post("/devices/{device_id}/revoke", dependencies=[Depends(require_local_caller)])
def revoke_device(device_id: int):
    row = _device_row(device_id)
    if not get_registry().revoke(device_id):
        raise HTTPException(status_code=404, detail="device not found or not currently trusted")
    if row:
        get_event_bus().publish_to(
            [f"device:{row['external_id']}", "device"],
            "device.updated",
            device_id=row["external_id"], device_name=row.get("device_name"), reason="revoked",
        )
    return {"revoked": True}


@router.post("/devices/{device_id}/rename", dependencies=[Depends(require_local_caller)])
def rename_device(device_id: int, req: RenameDeviceRequest):
    if not get_registry().rename(device_id, req.name):
        raise HTTPException(status_code=404, detail="device not found or not currently trusted")
    row = _device_row(device_id)
    if row:
        get_event_bus().publish_to(
            [f"device:{row['external_id']}", "device"],
            "device.updated",
            device_id=row["external_id"], device_name=row.get("device_name"), reason="renamed",
        )
    return {"renamed": True}


@router.put("/devices/{device_id}/capabilities")
def update_capabilities(device_id: str, req: CapabilitiesUpdateRequest,
                         device: dict = Depends(require_trusted_device)):
    """Device-authenticated and ownership-checked — a device may only
    ever report its own capabilities, never another device's."""
    if device["external_id"] != device_id:
        raise HTTPException(status_code=403, detail="a device may only update its own capabilities")
    try:
        get_registry().update_capabilities(device_id, req.capabilities, channel=DIRECT_CHANNEL)
    except CapabilityValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    get_event_bus().publish_to(
        [f"device:{device_id}", "device"],
        "device.updated", device_id=device_id, reason="capabilities",
    )
    return {"updated": True}


@router.post("/devices/{device_id}/heartbeat", response_model=HeartbeatResponse)
def heartbeat(device_id: str, device: dict = Depends(require_trusted_device)):
    """require_trusted_device already recorded this heartbeat (see its
    own docstring) — reaching this line at all *is* the liveness signal.
    What this adds on top: any task queued while the device was offline,
    redelivered now via get_pending_for_device (see connect/services/
    task_handoff.py's lifecycle diagram)."""
    if device["external_id"] != device_id:
        raise HTTPException(status_code=403, detail="device_id in path must match the authenticated device")
    pending = get_task_router().get_pending_for_device(device_id)
    return {
        "device_id": device_id,
        "connection_state": device["connection_state"],
        "pending_tasks": [asdict(t) for t in pending],
    }


# ─── Device tasks ────────────────────────────────────────────────────────

@router.post("/tasks", response_model=DeviceTaskRecord, status_code=201,
             dependencies=[Depends(require_local_caller)])
def create_device_task(req: DeviceTaskCreateRequest):
    """Desktop/Core-initiated — no device auth. This is the "Desktop ->
    Android" direction; "Android -> Desktop/Core" is the existing
    /api/iqoo/tasks (see this module's own docstring for why that's a
    separate, already-solved path rather than routed through here)."""
    try:
        task = get_task_router().create(
            origin="desktop", target_device_id=req.target_device_id, action=req.action,
            payload=req.payload, required_capability=req.required_capability,
            idempotency_key=req.idempotency_key, context_ref=req.context_ref,
            handoff_state=req.handoff_state, timeout_seconds=req.timeout_seconds,
        )
    except (UnknownDeviceError, CapabilityUnavailableError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.get("/tasks/{task_id}", response_model=DeviceTaskRecord)
def get_device_task(task_id: str):
    try:
        task = get_task_router().get(task_id)
    except TaskNotFoundError as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/ack", response_model=DeviceTaskRecord)
def ack_device_task(task_id: str, device: dict = Depends(require_trusted_device)):
    try:
        task = get_task_router().ack(task_id, device["external_id"])
    except (TaskNotFoundError, TaskNotOwnedByDeviceError, InvalidTaskStateError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/progress", response_model=DeviceTaskRecord)
def progress_device_task(task_id: str, req: TaskProgressRequest,
                          device: dict = Depends(require_trusted_device)):
    try:
        task = get_task_router().progress(task_id, device["external_id"], req.message, req.pct)
    except (TaskNotFoundError, TaskNotOwnedByDeviceError, InvalidTaskStateError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/action", response_model=DeviceTaskRecord)
def action_device_task(task_id: str, req: TaskActionRequest,
                        device: dict = Depends(require_trusted_device)):
    try:
        task = get_task_router().action(task_id, device["external_id"], req.description)
    except (TaskNotFoundError, TaskNotOwnedByDeviceError, InvalidTaskStateError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/verification", response_model=DeviceTaskRecord)
def verification_device_task(task_id: str, req: TaskVerificationRequest,
                              device: dict = Depends(require_trusted_device)):
    try:
        task = get_task_router().verification(task_id, device["external_id"], req.verified, req.detail)
    except (TaskNotFoundError, TaskNotOwnedByDeviceError, InvalidTaskStateError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/complete", response_model=DeviceTaskRecord)
def complete_device_task(task_id: str, req: TaskCompleteRequest,
                          device: dict = Depends(require_trusted_device)):
    try:
        task = get_task_router().complete(task_id, device["external_id"], req.result)
    except (TaskNotFoundError, TaskNotOwnedByDeviceError, InvalidTaskStateError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/fail", response_model=DeviceTaskRecord)
def fail_device_task(task_id: str, req: TaskFailRequest,
                      device: dict = Depends(require_trusted_device)):
    try:
        task = get_task_router().fail(task_id, device["external_id"], req.error)
    except (TaskNotFoundError, TaskNotOwnedByDeviceError, InvalidTaskStateError) as e:
        _raise_for_task_error(e)
    return asdict(task)


@router.post("/tasks/{task_id}/cancel", dependencies=[Depends(require_local_caller)])
def cancel_device_task(task_id: str, req: Optional[TaskCancelRequest] = None):
    """Desktop/Core-initiated, like create() — no device auth. A cancel
    racing a device's own completion is a normal outcome (returns
    cancelled=False, not an error) — see DeviceTaskRouter.cancel's own
    docstring."""
    try:
        cancelled = get_task_router().cancel(task_id, reason=req.reason if req else None)
    except TaskNotFoundError as e:
        _raise_for_task_error(e)
    return {"cancelled": cancelled}


@router.post("/tasks/{task_id}/handoff", response_model=DeviceTaskRecord,
             dependencies=[Depends(require_local_caller)])
def handoff_device_task(task_id: str, req: TaskHandoffRequest):
    """Desktop/Core-initiated. See connect/services/task_handoff.py's
    handoff() docstring — moves the task's thread to a new device without
    losing the original task_id's event history."""
    try:
        task = get_task_router().handoff(task_id, req.new_target_device_id, reason=req.reason)
    except (TaskNotFoundError, UnknownDeviceError, CapabilityUnavailableError) as e:
        _raise_for_task_error(e)
    return asdict(task)


# ─── Events (SSE) ────────────────────────────────────────────────────────

def _format_sse(event: dict) -> str:
    """Same framing as interfaces/api/server.py's _format_sse (the `id:`
    line is what makes the browser's native EventSource send Last-Event-ID
    automatically on reconnect). Duplicated locally rather than imported
    across modules — this repo's existing convention for small, stable,
    independent pieces (see e.g. tests/test_iqoo_phase3a_offline.py's own
    per-phase-file duplication)."""
    return f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n"


async def _connect_event_stream(stream: str, after_seq: int, request: Optional[Request] = None):
    """Same reconnect-safe shape as interfaces/api/server.py's
    event_stream(): replay backlog after `after_seq`, then block for new
    events. The terminal early-return only applies to "task:*" streams —
    "device"/"device:<id>"/"voice" streams never have a terminal event
    (see connect/core/events.py's TERMINAL_TASK_EVENT_TYPES, which is
    task-shaped by definition) and are expected to just keep running for
    as long as the client stays connected."""
    events = get_event_bus()
    seq = after_seq
    backlog = events.get_since(stream, seq)
    for event in backlog:
        seq = event["seq"]
        yield _format_sse(event)
        if stream.startswith("task:") and event["type"] in TERMINAL_TASK_EVENT_TYPES:
            return

    while True:
        if request is not None and await request.is_disconnected():
            return
        new_events = await asyncio.to_thread(events.wait_for_new, stream, seq, 1.0)
        if not new_events:
            if stream.startswith("task:") and events.has_terminal_event(stream):
                return
            yield ": heartbeat\n\n"
            continue
        for event in new_events:
            seq = event["seq"]
            yield _format_sse(event)
            if stream.startswith("task:") and event["type"] in TERMINAL_TASK_EVENT_TYPES:
                return


@router.get("/events")
async def stream_connect_events(stream: str, request: Request):
    """`stream` is any of the stream names connect/core/events.py's module
    docstring defines: "device", "device:<external_id>", "task:<task_id>",
    or "voice". Reconnect-safe via the standard Last-Event-ID header, same
    convention as GET /api/iqoo/tasks/{id}/events."""
    last_event_id = request.headers.get("last-event-id")
    after_seq = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
    return StreamingResponse(
        _connect_event_stream(stream, after_seq, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
