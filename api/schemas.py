"""
Request/response models for the VEDA localhost API (M8-A).

StatusResponse/ModelResponse are unchanged from Step 1. Everything
below is new for documents/knowledge/tasks/sovereignty/deliverable.

These are presentation shapes only — every field is either passed
straight through from a real dataclass already defined in the engine
(sovereign.knowledge.RetrievalResult, api.task_runner.ActivityStep/
TaskRecord, sovereign.security.network_guard.NetworkGuardReport) or
derived from real filesystem/glob state (DocumentInfo). Nothing here
invents data the engine doesn't already produce.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class StatusResponse(BaseModel):
    product: str
    assistant_display_name: str
    sovereign_mode: bool
    ollama_reachable: bool
    uptime_seconds: float
    last_task_id: Optional[str] = None  # lets a reloaded page recover task context


class ModelResponse(BaseModel):
    primary_model: str
    fallback_model: str
    active_model: Optional[str] = None
    status: str  # "ready" | "unavailable"
    detail: Optional[str] = None


# ─── documents ──────────────────────────────────────────────────────────

class DocumentInfo(BaseModel):
    filename: str
    file_type: str          # from sovereign.ingestion.extract.SUPPORTED_EXTENSIONS' values
    status: str              # "indexed" | "failed"
    chunk_count: int = 0
    detail: Optional[str] = None  # populated on status == "failed"


# ─── knowledge ──────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    top_k: int = 5


class SearchResultItem(BaseModel):
    text: str
    filename: str
    section: Optional[str] = None
    section_index: Optional[int] = None
    doc_id: Optional[str] = None
    relevance: float


class SearchResponse(BaseModel):
    available: bool  # False when the knowledge index has nothing indexed yet
    results: List[SearchResultItem] = []


# ─── tasks ──────────────────────────────────────────────────────────────

class TaskCreateRequest(BaseModel):
    task: str


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str


class ActivityStepResponse(BaseModel):
    step: int
    action: Optional[str] = None
    label: str
    observation: str
    success: Optional[bool] = None


class DeliverableInfo(BaseModel):
    filename: str
    sources: int = 0
    evidence_count: int = 0


class TaskStatusResponse(BaseModel):
    id: str
    task: str
    status: str  # queued | running | completed | incomplete | failed
    created_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    steps: List[ActivityStepResponse] = []
    result: Optional[str] = None
    error: Optional[str] = None
    deliverable: Optional[DeliverableInfo] = None
    has_sovereignty_report: bool = False


# ─── sovereignty ──────────────────────────────────────────────────────────

class SovereigntyResponse(BaseModel):
    task_id: str
    measured: bool  # False when the task ran with sovereign_mode off — "not measured", not "clean"
    report: Optional[Dict[str, Any]] = None  # NetworkGuardReport.to_dict(), passed through as-is

