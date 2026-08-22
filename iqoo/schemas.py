"""
iQOO — API Schemas (Phase 1)

Mirrors the task/event contract from the PDR section 8.4/8.5. Phase 1
accepts the full contract shape (so Phase 2 doesn't need a breaking
change) but only meaningfully executes "text" input_type — image/voice
attachments are stored and echoed back, not yet processed. See
docs/iqoo/PROGRESS.md.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field

InputType = Literal["text", "voice", "image", "image+text", "image+voice"]


class Attachment(BaseModel):
    kind: Literal["image", "audio"]
    # Phase 1: accepts a data URL or reference string. Real binary upload
    # (multipart) and vision/STT processing land in Phase 2.
    data: str = ""
    filename: Optional[str] = None


class TaskCreateRequest(BaseModel):
    instruction: str = Field(..., min_length=1, max_length=4000)
    input_type: InputType = "text"
    attachments: List[Attachment] = Field(default_factory=list)


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
    brain_reachable: bool
    active_task: Optional[str] = None
    queue_depth: int
    version: str = "iqoo-phase1"
