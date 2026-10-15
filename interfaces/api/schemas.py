"""
SAM Interfaces — API — Schemas (Phase 1 + Phase 2)

(Moved here in Phase 3A.5 — originated as iqoo/schemas.py; iqoo/schemas.py
now forwards here for backward compatibility. The HTTP contract itself —
routes, field names, and this version tag — is unchanged by the move.)

Mirrors the task/event contract from the PDR section 8.4/8.5. Phase 1
accepted the full contract shape but only executed "text" input_type.
Phase 2 adds real validation and processing for image/audio attachments
via multimodal/media_validation.py, multimodal/vision/adapter.py, and
multimodal/audio/adapter.py — the shape of TaskCreateRequest itself is
unchanged from Phase 1 (input_type and attachments already existed),
so an existing text-only POST body continues to work byte-for-byte
identically. The only shape change is on Attachment: mime_type is now
required, since Phase 1 never actually inspected attachment content and
Phase 2 must validate it before it reaches an AI model.
"""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from multimodal.media_validation import validate_attachment, AttachmentValidationError

InputType = Literal["text", "voice", "image", "image+text", "image+voice"]


class Attachment(BaseModel):
    kind: Literal["image", "audio"]
    mime_type: str
    # Phase 2: base64-encoded raw bytes (no "data:" URL prefix — the
    # client strips it before sending). Validated for MIME allowlist,
    # base64 well-formedness, and size limit at parse time so a bad
    # upload is rejected with a clear 422 before any task is created.
    data: str = ""
    filename: Optional[str] = None

    @model_validator(mode="after")
    def _validate_media(self):
        try:
            validate_attachment(self.kind, self.mime_type, self.data)
        except AttachmentValidationError as e:
            raise ValueError(str(e)) from e
        return self


class TaskCreateRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=4000)
    input_type: InputType = "text"
    attachments: List[Attachment] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_attachments_match_input_type(self):
        kinds = {a.kind for a in self.attachments}
        if self.input_type == "voice" and "audio" not in kinds:
            raise ValueError("input_type 'voice' requires an audio attachment")
        elif self.input_type in ("image", "image+text") and "image" not in kinds:
            raise ValueError(f"input_type '{self.input_type}' requires an image attachment")
        elif self.input_type == "image+voice" and not {"image", "audio"} <= kinds:
            raise ValueError("input_type 'image+voice' requires both an image and an audio attachment")
        # input_type == "text": attachments, if any, are simply unused —
        # matches Phase 1 behavior exactly, no validation needed.
        return self


class TaskRecord(BaseModel):
    task_id: str
    instruction: str
    input_type: str
    attachments: list
    status: str
    result_text: Optional[str] = None
    error: Optional[str] = None
    cancel_requested: bool
    created_at: str
    updated_at: str


class ExecutionEvent(BaseModel):
    type: str = "execution.step"
    task_id: str
    phase: str
    message: str
    timestamp: str


class HealthStatus(BaseModel):
    status: Literal["ok", "degraded"]
    worker_alive: bool
    brain_reachable: bool
    vision_model_available: Optional[bool] = None
    whisper_available: bool
    active_task: Optional[str] = None
    queue_depth: int
    uptime_seconds: float
    version: str = "iqoo-phase3a"


# ─── Brain / model selection (core/model_manager.py) ──────────────────────
# Served at /api/models, deliberately NOT under /api/iqoo/: choosing the
# Brain is SAM Core functionality, not part of the phone-task contract.
# interfaces/desktop/src/api/types.ts mirrors these field-for-field
# (tests/test_brain_model_management_offline.py checks the two stay in step).

class ModelInfo(BaseModel):
    name: str
    size_bytes: Optional[int] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    family: Optional[str] = None
    # Ollama's own /api/show capabilities ("completion", "tools", "vision",
    # "thinking", "embedding", ...); None when Ollama didn't report them.
    capabilities: Optional[List[str]] = None
    context_length: Optional[int] = None
    # Never "compatible": nothing in SAM can verify that -- see
    # core/model_manager.py's module docstring.
    compatibility: Literal["unknown", "incompatible"]
    compatibility_reason: str
    notes: List[str] = Field(default_factory=list)
    is_selected: bool
    is_fallback: bool
    is_active: bool


class BrainStatus(BaseModel):
    provider: str
    ollama_host: str
    status: Literal["ready", "unavailable"]
    detail: Optional[str] = None
    selected_model: str
    fallback_model: str
    # What Brain would use for the next request; None when neither the
    # selected nor the fallback model is installed (or Ollama is down).
    active_model: Optional[str] = None
    active_source: Optional[Literal["selected", "fallback"]] = None
    # The model Brain last actually sent a request to (None until the first
    # request after start-up).
    last_used_model: Optional[str] = None
    # True once the user chose the model; False means SAM's RAM-based default.
    user_selected: bool
    # True while a task is running/queued -- switching is refused then.
    busy: bool
    # Subsystems pinned to their own model (planner/reflection/
    # founder_classifier); they do not follow a Brain switch.
    overrides: Dict[str, str] = Field(default_factory=dict)
    models: List[ModelInfo] = Field(default_factory=list)


class ModelSelectRequest(BaseModel):
    model: str = Field(..., min_length=1, max_length=200)


class ModelPullRequest(BaseModel):
    """Model identifier for the streaming Ollama pull endpoint."""
    model: str = Field(..., min_length=1, max_length=200)
