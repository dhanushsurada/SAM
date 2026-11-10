"""
SAM Unified Cross-Device Task Coordinator

Coordinates end-to-end task execution across desktop and mobile devices:
- Central capability discovery and availability tracking
- Intelligent capability-based task routing (Desktop vs Android)
- Leased execution ownership (prevents duplicate execution upon reconnect)
- Multi-step cross-device handoffs (e.g., Desktop file search -> Phone receive,
  Phone notifications -> Desktop report generation)
- State persistence and event streaming
"""

import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

from connect.core.capabilities import (
    KNOWN_CAPABILITIES, device_supports,
    VOICE, NOTIFICATIONS, APP_LAUNCH, CAMERA, DEVICE_CONTROL,
    MODEL_INFERENCE, FILE_TRANSFER, ACCESSIBILITY, UI_INTERACTION,
    BROWSER, TERMINAL, DOCUMENTS,
)
from connect.core.device_registry import DeviceRegistry
from connect.services.task_handoff import DeviceTaskRouter, DeviceTask

logger = logging.getLogger("SAM.Connect.Coordinator")

DEFAULT_LEASE_DURATION_SECONDS = 60.0


@dataclass
class ExecutionLease:
    lease_id: str
    task_id: str
    owner_device_id: str  # "desktop" or external device UUID
    granted_at: float
    expires_at: float
    revoked: bool = False

    @property
    def is_active(self) -> bool:
        return not self.revoked and time.time() < self.expires_at

    def renew(self, duration_seconds: float = DEFAULT_LEASE_DURATION_SECONDS):
        if not self.revoked:
            self.expires_at = time.time() + duration_seconds


@dataclass
class CoordinatedTask:
    task_id: str
    goal: str
    origin_device_id: str
    current_device_id: str
    required_capabilities: List[str]
    status: str  # "created" | "leased" | "executing" | "transferring" | "completed" | "failed" | "cancelled"
    lease: Optional[ExecutionLease] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    handoff_history: List[str] = field(default_factory=list)
    idempotency_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.lease:
            d["lease"] = {
                "lease_id": self.lease.lease_id,
                "owner": self.lease.owner_device_id,
                "expires_at": self.lease.expires_at,
                "is_active": self.lease.is_active
            }
        return d


class UnifiedTaskCoordinator:
    """
    Central brain for cross-device awareness and task ownership.
    Works seamlessly with DeviceRegistry and DeviceTaskRouter.
    """

    def __init__(self, registry: DeviceRegistry, router: DeviceTaskRouter):
        self.registry = registry
        self.router = router
        self._tasks: Dict[str, CoordinatedTask] = {}
        self._idempotency_map: Dict[str, str] = {}  # idempotency_key -> task_id
        self._desktop_device_id = "desktop"

    def get_desktop_capabilities(self) -> Dict[str, Dict[str, Any]]:
        """Desktop built-in capabilities."""
        return {
            BROWSER: {"available": True, "permission": "granted"},
            TERMINAL: {"available": True, "permission": "granted"},
            DOCUMENTS: {"available": True, "permission": "granted"},
            DEVICE_CONTROL: {"available": True, "permission": "granted"},
            MODEL_INFERENCE: {"available": True, "permission": "granted"},
            FILE_TRANSFER: {"available": True, "permission": "granted"},
            VOICE: {"available": True, "permission": "granted"},
        }

    def get_device_capabilities(self, device_id: str) -> Dict[str, Dict[str, Any]]:
        if device_id == self._desktop_device_id:
            return self.get_desktop_capabilities()
        device = self.registry.get_device(device_id)
        if not device:
            return {}
        return device.get("capabilities", {})

    def select_best_device_for_capability(self, capability: str) -> Tuple[Optional[str], str]:
        """
        Determines whether desktop or an active paired mobile device should execute
        a specific capability.
        Returns (device_id, reason).
        """
        # Capabilities exclusive to Android / mobile
        if capability in (NOTIFICATIONS, APP_LAUNCH, ACCESSIBILITY, UI_INTERACTION):
            # Look for an online trusted mobile device supporting it
            devices = self.registry.list_devices()
            online_supported = [
                d for d in devices
                if d.get("is_trusted") and d.get("connection_state") == "online"
                and device_supports(d.get("capabilities", {}), capability)
            ]
            if online_supported:
                chosen = online_supported[0]
                return chosen["device_id"], f"Selected online mobile device '{chosen.get('name')}' for {capability}"
            
            # If no online device, look for trusted paired device even if offline (will queue)
            paired = [
                d for d in devices
                if d.get("is_trusted") and device_supports(d.get("capabilities", {}), capability)
            ]
            if paired:
                chosen = paired[0]
                return chosen["device_id"], f"Selected mobile device '{chosen.get('name')}' (currently offline, will queue)"
            
            return None, f"No paired mobile device supports capability '{capability}'"

        # Capabilities native to desktop
        if capability in (BROWSER, TERMINAL, DOCUMENTS):
            return self._desktop_device_id, f"Capability '{capability}' requires desktop environment"

        # General / dual capabilities (e.g. MODEL_INFERENCE, FILE_TRANSFER, VOICE)
        # Default to desktop if available, or mobile if desktop is not preferred
        return self._desktop_device_id, f"Defaulting to desktop for '{capability}'"

    def create_coordinated_task(
        self,
        goal: str,
        origin_device_id: str = "desktop",
        target_device_id: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        idempotency_key: Optional[str] = None
    ) -> CoordinatedTask:
        """
        Creates and registers a new cross-device coordinated task with an execution lease.
        """
        if idempotency_key and idempotency_key in self._idempotency_map:
            existing_id = self._idempotency_map[idempotency_key]
            return self._tasks[existing_id]

        req_caps = required_capabilities or []
        
        # Auto-route if target not specified
        if not target_device_id:
            if req_caps:
                target_device_id, reason = self.select_best_device_for_capability(req_caps[0])
            else:
                target_device_id = origin_device_id

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        
        # Grant initial lease
        lease = ExecutionLease(
            lease_id=f"lease_{uuid.uuid4().hex[:8]}",
            task_id=task_id,
            owner_device_id=target_device_id or origin_device_id,
            granted_at=time.time(),
            expires_at=time.time() + DEFAULT_LEASE_DURATION_SECONDS
        )

        task = CoordinatedTask(
            task_id=task_id,
            goal=goal,
            origin_device_id=origin_device_id,
            current_device_id=target_device_id or origin_device_id,
            required_capabilities=req_caps,
            status="leased",
            lease=lease,
            idempotency_key=idempotency_key
        )

        self._tasks[task_id] = task
        if idempotency_key:
            self._idempotency_map[idempotency_key] = task_id

        logger.info(f"Created CoordinatedTask {task_id} assigned to {task.current_device_id} (lease={lease.lease_id})")
        return task

    def transfer_task(
        self,
        task_id: str,
        to_device_id: str,
        step_result: Optional[Any] = None,
        next_goal: Optional[str] = None
    ) -> CoordinatedTask:
        """
        Handoff an active task from one device to another (e.g. desktop file search -> mobile display).
        Safely revokes old lease and grants new lease to target device.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Record step completion
        task.steps.append({
            "device_id": task.current_device_id,
            "status": "handed_off",
            "result": step_result,
            "timestamp": time.time()
        })
        task.handoff_history.append(task.current_device_id)

        # Revoke previous lease
        if task.lease:
            task.lease.revoked = True

        # Issue new lease to target device
        new_lease = ExecutionLease(
            lease_id=f"lease_{uuid.uuid4().hex[:8]}",
            task_id=task_id,
            owner_device_id=to_device_id,
            granted_at=time.time(),
            expires_at=time.time() + DEFAULT_LEASE_DURATION_SECONDS
        )

        task.current_device_id = to_device_id
        task.lease = new_lease
        task.status = "transferring"
        task.updated_at = time.time()
        if next_goal:
            task.goal = next_goal

        logger.info(f"Task {task_id} transferred to {to_device_id} (new lease={new_lease.lease_id})")
        return task

    def complete_task(self, task_id: str, result: Any) -> CoordinatedTask:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = "completed"
        task.result = result
        task.updated_at = time.time()
        if task.lease:
            task.lease.revoked = True
        logger.info(f"Task {task_id} completed successfully")
        return task

    def fail_task(self, task_id: str, error: str) -> CoordinatedTask:
        task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = "failed"
        task.error = error
        task.updated_at = time.time()
        if task.lease:
            task.lease.revoked = True
        logger.warning(f"Task {task_id} failed: {error}")
        return task

    def get_task(self, task_id: str) -> Optional[CoordinatedTask]:
        return self._tasks.get(task_id)
