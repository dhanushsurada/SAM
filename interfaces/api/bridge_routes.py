"""
SAM Interfaces — API — Omnichannel Bridge & Apple iOS Routes

Provides HTTP endpoints for:
1. Omnichannel Bridge status, control & pairing (Telegram, WhatsApp, Android, iOS)
2. WhatsApp Webhook (GET verification challenge & POST events)
3. Apple iOS Siri & Action Button API (/api/ios/shortcut)
4. Apple Shortcuts template & setup config
5. Cross-Device Shared Clipboard & Fabric Topology
"""

import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from connect.bridges.omnichannel_manager import get_bridge_manager
from connect.bridges.apple_ios.shortcuts_bridge import IOSShortcutRequest

logger = logging.getLogger("SAM.API.BridgeRoutes")

router = APIRouter(tags=["bridges"])


# ─── Pydantic Schemas ───────────────────────────────────────────────────────

class ShortcutInput(BaseModel):
    prompt: str = Field(..., description="User voice transcript or text command from iPhone Siri / Action Button")
    voice_response: bool = Field(False, description="Whether to return base64 WAV audio for Siri to speak")
    device_model: Optional[str] = Field("iPhone", description="e.g. iPhone 16 Pro, iPad Pro, Apple Watch")
    battery_level: Optional[float] = Field(None, description="Battery percentage (0.0 to 1.0)")


class ClipboardPayload(BaseModel):
    content: str
    source_device_id: Optional[str] = "desktop"
    mime_type: Optional[str] = "text/plain"


class BroadcastRequest(BaseModel):
    text: str
    channels: Optional[List[str]] = None


# ─── Omnichannel Status & Control ──────────────────────────────────────────

@router.get("/api/bridges/status")
def get_bridges_status():
    """Returns real-time status of all messaging and phone companion bridges."""
    mgr = get_bridge_manager()
    return mgr.get_status()


@router.post("/api/bridges/{channel}/start")
def start_bridge(channel: str):
    """Starts a specific bridge (e.g. telegram, whatsapp)."""
    mgr = get_bridge_manager()
    res = mgr.start_channel(channel.lower())
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to start bridge"))
    return res


@router.post("/api/bridges/{channel}/stop")
def stop_bridge(channel: str):
    """Stops a specific bridge."""
    mgr = get_bridge_manager()
    return mgr.stop_channel(channel.lower())


@router.post("/api/bridges/{channel}/pair")
def generate_channel_pairing(channel: str, request: Request):
    """Generates pairing code, deep link, or QR payload for any channel."""
    mgr = get_bridge_manager()
    host_url = str(request.base_url).rstrip("/")
    res = mgr.generate_pairing_info(channel.lower(), host_url=host_url)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res


@router.post("/api/bridges/broadcast")
def broadcast_announcement(req: BroadcastRequest):
    """Dispatches a message simultaneously across connected Telegram, WhatsApp, and companion channels."""
    mgr = get_bridge_manager()
    return mgr.broadcast_message(req.text, channels=req.channels)


# ─── WhatsApp Webhook ──────────────────────────────────────────────────────

@router.get("/api/bridges/whatsapp/webhook")
def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta WhatsApp Cloud API webhook verification challenge handshake."""
    mgr = get_bridge_manager()
    challenge = mgr.whatsapp.verify_webhook(hub_mode, hub_verify_token, hub_challenge)
    if challenge is not None:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/api/bridges/whatsapp/webhook")
async def receive_whatsapp_webhook(request: Request):
    """Inbound Meta WhatsApp Cloud API event notifications."""
    mgr = get_bridge_manager()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    result = mgr.whatsapp.handle_webhook_payload(body)
    return {"status": "ok", "result": result}


# ─── Apple iOS Siri & Action Button API ────────────────────────────────────

@router.post("/api/ios/shortcut")
def execute_ios_shortcut(req: ShortcutInput):
    """
    Direct Siri / Action Button execution endpoint for Apple iOS.
    Returns spoken text response, action outcome, and optional base64 audio.
    """
    mgr = get_bridge_manager()
    shortcut_req = IOSShortcutRequest(
        prompt=req.prompt,
        voice_response=req.voice_response,
        device_model=req.device_model,
        battery_level=req.battery_level
    )
    res = mgr.apple_ios.handle_shortcut_request(shortcut_req)
    return res.to_dict()


@router.get("/api/ios/shortcut/config")
def get_ios_shortcut_config(request: Request):
    """
    Returns the ready-to-use Apple Shortcuts definition and 1-click import payload.
    """
    mgr = get_bridge_manager()
    host_url = str(request.base_url).rstrip("/")
    return mgr.apple_ios.generate_apple_shortcut_definition(host_url=host_url)


# ─── Device Fabric & Shared Clipboard ──────────────────────────────────────

@router.get("/api/fabric/topology")
def get_fabric_topology():
    """Returns the unified multi-device mesh topology (Desktop, Android, iPhone, Telegram, WhatsApp)."""
    mgr = get_bridge_manager()
    return mgr.fabric.get_topology()


@router.get("/api/fabric/clipboard")
def get_shared_clipboard():
    """Reads cross-device synchronized clipboard."""
    mgr = get_bridge_manager()
    return mgr.fabric.get_clipboard()


@router.post("/api/fabric/clipboard")
def set_shared_clipboard(payload: ClipboardPayload):
    """Updates cross-device synchronized clipboard."""
    mgr = get_bridge_manager()
    return mgr.fabric.set_clipboard(
        content=payload.content,
        source_device_id=payload.source_device_id or "desktop",
        mime_type=payload.mime_type or "text/plain"
    )
