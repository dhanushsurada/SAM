"""
SAM Unified Device Fabric & Matter Flow

Manages cross-device topology, real-time presence, cross-device shared clipboard,
and seamless multi-device task handoff across:
- Desktop (macOS / Windows)
- Android (sam-android Companion via LAN & Remote Relay)
- Apple iOS (iPhone / iPad / Apple Watch via Siri Shortcuts & Continuity)
- Messaging Bridges (Telegram, WhatsApp)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from connect.core.device_registry import DeviceRegistry, DIRECT_CHANNEL
from connect.services.task_handoff import DeviceTaskRouter

logger = logging.getLogger("SAM.Connect.Fabric")


@dataclass
class SharedClipboard:
    content: str = ""
    source_device_id: str = "desktop"
    updated_at: float = field(default_factory=time.time)
    mime_type: str = "text/plain"


@dataclass
class FabricNode:
    device_id: str
    name: str
    device_type: str  # "desktop" | "android" | "iphone" | "telegram" | "whatsapp"
    channel: str
    is_online: bool
    capabilities: List[str]
    last_seen: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class DeviceFabric:
    """
    Central state fabric connecting all ecosystem nodes and managing
    matter flows between mobile, messaging, and desktop agents.
    """

    def __init__(self, registry: Optional[DeviceRegistry] = None, task_router: Optional[DeviceTaskRouter] = None):
        self.registry = registry or DeviceRegistry()
        self.task_router = task_router
        self._clipboard = SharedClipboard()
        self._active_matter_flows: List[Dict[str, Any]] = []

    def get_topology(self) -> Dict[str, Any]:
        """
        Returns full mesh topology of connected nodes across all channels.
        """
        nodes: List[Dict[str, Any]] = []

        # 1. Host Desktop Node
        nodes.append({
            "device_id": "desktop_primary",
            "name": "Host SAM (macOS)",
            "device_type": "desktop",
            "channel": "local",
            "is_online": True,
            "capabilities": ["browser", "terminal", "documents", "device-control", "model-inference", "voice"],
            "last_seen": time.time(),
            "metadata": {"role": "coordinator", "status": "active"}
        })

        # 2. Registered Trusted Devices from Registry
        trusted = self.registry.list_devices(include_pending=False)
        for d in trusted:
            channel = d.get("channel", "unknown")
            platform_str = (d.get("platform") or "").lower()

            if channel == "telegram":
                dtype = "telegram"
            elif channel == "whatsapp":
                dtype = "whatsapp"
            elif "ios" in platform_str or "iphone" in platform_str or "apple" in platform_str:
                dtype = "iphone"
            elif "android" in platform_str:
                dtype = "android"
            else:
                dtype = "mobile_node"

            caps = list(d.get("capabilities", {}).keys()) if isinstance(d.get("capabilities"), dict) else []
            is_online = d.get("connection_state") == "online" or channel in ("telegram", "whatsapp")

            nodes.append({
                "device_id": d.get("external_id") or str(d.get("id")),
                "name": d.get("device_name") or f"{dtype.capitalize()} Node",
                "device_type": dtype,
                "channel": channel,
                "is_online": is_online,
                "capabilities": caps,
                "last_seen": d.get("last_active") or d.get("paired_at"),
                "metadata": {
                    "protocol_version": d.get("protocol_version", "1.0"),
                    "status": d.get("status")
                }
            })

        return {
            "total_nodes": len(nodes),
            "online_nodes": sum(1 for n in nodes if n["is_online"]),
            "nodes": nodes,
            "active_flows": len(self._active_matter_flows),
            "clipboard_synced_at": self._clipboard.updated_at
        }

    # ─── Cross-Device Shared Clipboard ────────────────────────────────────

    def set_clipboard(self, content: str, source_device_id: str = "desktop", mime_type: str = "text/plain") -> Dict[str, Any]:
        """Updates cross-device shared clipboard."""
        self._clipboard = SharedClipboard(
            content=content,
            source_device_id=source_device_id,
            updated_at=time.time(),
            mime_type=mime_type
        )
        logger.info(f"Shared clipboard updated from {source_device_id} ({len(content)} chars)")
        return {
            "synced": True,
            "updated_at": self._clipboard.updated_at,
            "source": source_device_id
        }

    def get_clipboard(self) -> Dict[str, Any]:
        """Reads cross-device shared clipboard."""
        return {
            "content": self._clipboard.content,
            "source_device_id": self._clipboard.source_device_id,
            "updated_at": self._clipboard.updated_at,
            "mime_type": self._clipboard.mime_type
        }

    # ─── Matter Flow Handoff ──────────────────────────────────────────────

    def initiate_matter_flow(
        self,
        flow_name: str,
        origin_channel: str,
        target_device_id: str,
        action: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Orchestrates an end-to-end task flow across channels.
        Example: WhatsApp prompt -> Desktop ReAct -> Android App launch -> Result back to WhatsApp.
        """
        flow_id = f"flow_{int(time.time()*1000)}"
        flow_record = {
            "flow_id": flow_id,
            "name": flow_name,
            "origin_channel": origin_channel,
            "target_device_id": target_device_id,
            "action": action,
            "status": "in_progress",
            "created_at": time.time(),
            "updated_at": time.time()
        }
        self._active_matter_flows.append(flow_record)
        logger.info(f"Initiated matter flow: {flow_name} ({origin_channel} -> {target_device_id})")
        return flow_record

    def complete_matter_flow(self, flow_id: str, success: bool, result_summary: str = ""):
        for f in self._active_matter_flows:
            if f["flow_id"] == flow_id:
                f["status"] = "completed" if success else "failed"
                f["result_summary"] = result_summary
                f["updated_at"] = time.time()
                break
