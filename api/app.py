"""
VEDA localhost API — M8-A.

Thin FastAPI adapter over the existing SAM engine. This file contains
NO business/agent logic of its own — every handler below either reads
a value straight from an existing engine object (Settings, Identity,
Brain, VectorIndex) or delegates to api/task_runner.py and api/
uploads.py, both of which are plain Python with no fastapi dependency
and are exercised directly in tests/test_api_task_runner_offline.py
and tests/test_api_uploads_offline.py — real execution against the
real engine, not just this file's own (unexecuted, see below) logic.

Binding: 127.0.0.1 only, e.g.:
    uvicorn api.app:app --host 127.0.0.1 --port 8420
Never bind 0.0.0.0 — the product's core claim is that nothing leaves
this machine, and a wildcard bind would put that claim at risk on
whatever network the demo machine happens to be on.

No auth, no websockets, no persistence beyond the process's lifetime,
no telemetry, no external calls, no multi-user support — all
deliberately out of scope (M8-A brief, "do not add unnecessary
authentication to a localhost-only SIH prototype").

Verification note: this file itself could not be executed in the
sandbox this was built in — fastapi/uvicorn aren't installable there
(no network access; confirmed via three separate install attempts).
Every function it calls (TaskManager, save_uploaded_file, index_file,
search_knowledge, NetworkGuardReport.to_dict) has been independently
verified against the real engine in tests/test_api_task_runner_offline.py
and tests/test_api_uploads_offline.py, both of which DID run. What
remains unverified is purely the HTTP shell around them: status codes,
JSON serialization of the pydantic models, and multipart upload
parsing. Run tests/test_api_status_model_offline.py and the manual
checklist in the delivery notes on a machine with these packages
installed before treating this file itself as proven.
"""

import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import state
from api.schemas import (
    ActivityStepResponse,
    DeliverableInfo,
    DocumentInfo,
    ModelResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SovereigntyResponse,
    StatusResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from api.task_runner import TaskBusyError
from api.uploads import UploadValidationError, save_uploaded_file
from sovereign.ingestion.extract import SUPPORTED_EXTENSIONS
from sovereign.knowledge import index_file, search_knowledge

# Re-bound under the old Step-1 names so tests/test_api_status_model_offline.py's
# patch("api.app._brain._check_ollama", ...) / patch("api.app._brain._ensure_model", ...)
# keep working unchanged — these are the exact same objects as api.state.*,
# not copies, so patching an attribute on either name affects the one
# real instance either way.
_settings = state.settings
_identity = state.identity
_brain = state.brain
_vector_index = state.vector_index
_task_manager = state.task_manager

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
_STARTED_AT = time.monotonic()

app = FastAPI(title="VEDA API", version="0.2.0")


# ─── status / model (Step 1 — behavior unchanged) ──────────────────────────

@app.get("/api/status", response_model=StatusResponse)
def get_status() -> StatusResponse:
    """Read-only snapshot. ollama_reachable is a cheap probe
    (Brain._check_ollama — GET /api/tags, 3s timeout, no side effects)."""
    identity_data = _identity.load()
    return StatusResponse(
        product=state.PRODUCT_NAME,
        assistant_display_name=identity_data.get("assistant_name", "VEDA"),
        sovereign_mode=_settings.sovereign_mode,
        ollama_reachable=_brain._check_ollama(),
        uptime_seconds=time.monotonic() - _STARTED_AT,
        last_task_id=_task_manager.last_task_id,
    )


@app.get("/api/model", response_model=ModelResponse)
def get_model() -> ModelResponse:
    """Read-only model check. Brain._ensure_model() only lists
    already-pulled models via Ollama's /api/tags — never calls
    /api/pull, never mutates Settings. Reports status="unavailable"
    instead of a 500 when Ollama is down or neither model is present —
    an expected demo-day state, not a server error."""
    try:
        active = _brain._ensure_model()
        return ModelResponse(
            primary_model=_settings.primary_model,
            fallback_model=_settings.fallback_model,
            active_model=active,
            status="ready",
        )
    except RuntimeError as e:
        return ModelResponse(
            primary_model=_settings.primary_model,
            fallback_model=_settings.fallback_model,
            active_model=None,
            status="unavailable",
            detail=str(e),
        )


# ─── documents (M1 ingestion, exposed) ─────────────────────────────────────

@app.post("/api/documents", response_model=DocumentInfo)
async def upload_document(file: UploadFile = File(...)) -> DocumentInfo:
    """upload -> validate -> safely store -> ingest -> index -> report
    status. Validation (type/size/name/traversal) happens in
    api/uploads.py, entirely separate from the document-trust boundary
    (wrap_untrusted) applied later, inside read_document/search_knowledge,
    the moment content actually reaches an LLM prompt — this endpoint
    never constructs a prompt, so that boundary doesn't apply here and
    isn't duplicated here either."""
    try:
        saved_path = save_uploaded_file(file, _settings.sovereign_docs_dir)
    except UploadValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    file_type = SUPPORTED_EXTENSIONS.get(saved_path.suffix.lower(), "unknown")
    display_name = file.filename or saved_path.name

    try:
        chunk_count = index_file(saved_path, _settings, index=_vector_index)
        info = DocumentInfo(filename=display_name, file_type=file_type,
                             status="indexed", chunk_count=chunk_count)
    except Exception as e:
        # A corrupt/unreadable file is a real, expected outcome here —
        # reported as a failed DocumentInfo, not a 500.
        info = DocumentInfo(filename=display_name, file_type=file_type,
                             status="failed", detail=str(e))

    with state.documents_lock:
        state.documents.append(info.model_dump())
    return info


@app.get("/api/documents", response_model=list[DocumentInfo])
def list_documents() -> list:
    with state.documents_lock:
        return list(state.documents)


# ─── knowledge (M2 retrieval, exposed) ─────────────────────────────────────

@app.post("/api/knowledge/search", response_model=SearchResponse)
def search(req: SearchRequest) -> SearchResponse:
    """Calls the same module-level search_knowledge() the
    search_knowledge TOOL calls internally — real embedding + real
    Chroma query, no reimplementation here. available=False (not an
    error) when nothing has been indexed yet, matching what the tool
    itself checks before running a query."""
    if not _vector_index.available:
        return SearchResponse(available=False, results=[])
    raw = search_knowledge(req.query, _vector_index, req.top_k)
    return SearchResponse(
        available=True,
        results=[
            SearchResultItem(text=r.text, filename=r.filename, section=r.section,
                              section_index=r.section_index, doc_id=r.doc_id,
                              relevance=r.relevance)
            for r in raw
        ],
    )


# ─── tasks (M3/M6 ReAct + Sovereign workflow, exposed) ─────────────────────

@app.post("/api/tasks", response_model=TaskCreateResponse, status_code=202)
def create_task(req: TaskCreateRequest) -> TaskCreateResponse:
    """Starts the real run_task_with_optional_sovereign_mode() in a
    background thread via TaskManager (api/task_runner.py — verified
    directly against the real engine, see that test file). Serialized:
    only one sovereign task may run at a time (see TaskManager's
    docstring for why), so a second submission gets 409, not queued."""
    try:
        record = _task_manager.start_task(req.task)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TaskBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return TaskCreateResponse(task_id=record.id, status=record.status)


def _task_to_response(record) -> TaskStatusResponse:
    deliverable = None
    if record.deliverable:
        deliverable = DeliverableInfo(
            filename=record.deliverable["filename"],
            sources=record.deliverable.get("sources", 0),
            evidence_count=record.deliverable.get("evidence_count", 0),
        )
    return TaskStatusResponse(
        id=record.id,
        task=record.task_text,
        status=record.status,
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        steps=[
            ActivityStepResponse(step=s.step, action=s.action, label=s.label,
                                  observation=s.observation, success=s.success)
            for s in record.steps
        ],
        result=record.result,
        error=record.error,
        deliverable=deliverable,
        has_sovereignty_report=record.sovereignty is not None,
    )


@app.get("/api/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    record = _task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    return _task_to_response(record)


@app.get("/api/tasks/{task_id}/deliverable", response_model=DeliverableInfo)
def get_deliverable(task_id: str) -> DeliverableInfo:
    record = _task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    if record.deliverable is None:
        raise HTTPException(status_code=404, detail="No deliverable produced for this task (yet, or at all)")
    return DeliverableInfo(
        filename=record.deliverable["filename"],
        sources=record.deliverable.get("sources", 0),
        evidence_count=record.deliverable.get("evidence_count", 0),
    )


@app.get("/api/tasks/{task_id}/deliverable/file")
def get_deliverable_file(task_id: str):
    path = _task_manager.deliverable_file_path(task_id)
    if path is None:
        raise HTTPException(status_code=404, detail="No deliverable file available for this task")
    return FileResponse(
        path=str(path),
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ─── sovereignty (M5 NetworkGuard report, exposed) ─────────────────────────

@app.get("/api/sovereignty/{task_id}", response_model=SovereigntyResponse)
def get_sovereignty(task_id: str) -> SovereigntyResponse:
    """measured=False (not an error, not "unsafe") when the task ran
    with sovereign_mode off — Settings controls that globally today;
    M8-A doesn't add a way to toggle it per-request, since no such
    capability exists in the engine."""
    record = _task_manager.get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown task_id")
    return SovereigntyResponse(
        task_id=task_id,
        measured=record.sovereignty is not None,
        report=record.sovereignty,
    )


# ─── static frontend — MUST be mounted last ────────────────────────────────
# Starlette matches routes in registration order. Every @app.get/@app.post
# above is registered before this Mount("/"), so requests to /api/* are
# matched by their specific routes first; this catch-all only serves
# whatever's left. Moving this mount earlier in the file would silently
# break every API route above it — don't reorder this file.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
