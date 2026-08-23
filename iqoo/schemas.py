"""
iQOO — API Schemas (Phase 1 + Phase 2)

Mirrors the task/event contract from the PDR section 8.4/8.5. Phase 1
accepted the full contract shape but only executed "text" input_type.
Phase 2 adds real validation and processing for image/audio attachments
via iqoo/media_validation.py, iqoo/vision_adapter.py, and
iqoo/audio_adapter.py — the shape of TaskCreateRequest itself is
unchanged from Phase 1 (input_type and attachments already existed),
so an existing text-only POST body continues to work byte-for-byte
identically. The only shape change is on Attachment: mime_type is now
required, since Phase 1 never actually inspected attachment content and
Phase 2 must validate it before it reaches an AI model.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field, model_validator

from iqoo.media_validation import validate_attachment, AttachmentValidationError

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
