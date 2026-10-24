"""
SAM Interfaces — API — Phone Task Gateway Server (Phase 1 + Phase 2 + Phase 3A)

(Moved here in Phase 3A.5 — originated as iqoo/server.py; iqoo/server.py
now forwards here, including its `python -m iqoo.server` executable
entry point, for backward compatibility.)

Standalone process, same philosophy as interfaces/telegram/telegram_bridge.py:
it does NOT run inside main.py's voice/text loop, and main.py is completely
untouched by this branch. Run it alongside (or instead of) SAM's voice
loop:

    python -m interfaces.api.server      (canonical)
    python -m iqoo.server                (still works — compatibility shim)

Serves:
- POST   /api/iqoo/tasks                submit a task
- GET    /api/iqoo/tasks/{id}           poll task status
- GET    /api/iqoo/tasks/{id}/events    SSE execution progress stream (reconnect-safe, Phase 3A)
- POST   /api/iqoo/tasks/{id}/cancel    cancel a running/queued task
- POST   /api/iqoo/tasks/{id}/retry     resubmit as a fresh task
- GET    /api/iqoo/health               liveness + queue/brain/model diagnostics (Phase 3A)
- POST   /api/iqoo/demo/reset           clear all task state (Phase 3A, demo-scoped)
- GET    /api/models                    Brain: provider status, selected/fallback/active model,
                                        installed models + compatibility (core/model_manager.py)
- POST   /api/models/select             make an installed model the Brain (409 while a task runs)
- POST   /api/models/pull               stream model-download progress (loopback only)
- /                                     the phone client (interfaces/web/)

(The /api/models routes are SAM Core, not phone-task API, so they sit beside
/api/iqoo/* rather than under it -- the /api/iqoo/* contract is unchanged.)
"""

import asyncio
import json
import logging
import math
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from config.settings import Settings, validate_assistant_name

from core.model_manager import (
    ModelIncompatibleError, ModelManagerError, ModelMetadataError,
    ModelNotInstalledError, OllamaUnavailableError, ModelPullError,
)
from interfaces.api.gateway import (
    TaskGateway, TaskAlreadyActiveError, DemoResetBusyError, BrainBusyError,
)
from interfaces.api.task_store import TERMINAL_STATUSES
from interfaces.api.schemas import (
    TaskCreateRequest, TaskRecord, HealthStatus, BrainStatus, ModelSelectRequest, ModelPullRequest,
)
# agent/cross-device: /api/connect/* — device pairing, trust, capabilities
# and cross-device task routing. Pure addition; every /api/iqoo/* route
# above and below this import is unchanged. See
# interfaces/api/connect_routes.py's own module docstring and
# docs/architecture/CROSS_DEVICE_PROTOCOL.md for the full contract.
from interfaces.api.connect_routes import (
    router as connect_router,
    start_background_tasks as _start_connect_background_tasks,
    stop_background_tasks as _stop_connect_background_tasks,
    require_local_caller,
)
from runtime.environment_manager import EnvironmentCompatibilityManager

logger = logging.getLogger("SAM.iQOO.Server")


class EnvironmentRepairRequest(BaseModel):
    groups: list[str]

# interfaces/api/server.py -> interfaces/api -> interfaces -> repo root.
# (One level deeper than the old iqoo/server.py -> iqoo -> repo root, since
# this file now lives one directory deeper.)
BASE_DIR = Path(__file__).parent.parent.parent
CLIENT_DIR = BASE_DIR / "interfaces" / "web"

app = FastAPI(title="SAM iQOO Phone Gateway", version="iqoo-phase3a")
# The packaged Tauri webview has a distinct origin and cannot use Vite's
# development proxy. Keep CORS limited to Tauri v2's platform origins and
# the local Vite development server; this is transport configuration, not
# an authentication boundary.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
        "http://localhost:5173", "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Last-Event-ID", "X-SAM-Device", "X-SAM-Timestamp", "X-SAM-Nonce", "X-SAM-Signature"],
)
app.include_router(connect_router)  # agent/cross-device: /api/connect/*

_gateway: TaskGateway = None  # constructed lazily on first request / at startup


def get_gateway() -> TaskGateway:
    global _gateway
    if _gateway is None:
        _gateway = TaskGateway()
    return _gateway


# Only fields represented by the desktop's editable settings form may be
# changed through this local-only endpoint. Paths and detected hardware are
# derived by SAM and intentionally remain read-only.
SETTINGS_EDITABLE_FIELDS = {
    "assistant_name", "user_name", "ollama_host", "model_context_length",
    "temperature", "max_tokens", "wake_word", "wake_word_threshold",
    "whisper_model", "whisper_device", "recording_timeout",
    "silence_threshold", "tts_engine", "kokoro_voice", "piper_model",
    "speech_rate", "vision_model", "screenshot_quality", "memory_top_k",
    "embedding_model", "founder_mode_enabled", "founder_mode_llm_capture",
    "founder_mode_classifier_model", "founder_mode_min_confidence_to_show",
    "planner_model", "reflection_model", "allow_risky_terminal_commands",
    "telegram_bot_token", "telegram_bot_username", "incognito", "log_level",
    "license_enforcement_enabled", "api_auth_token",
}
SETTINGS_READ_ONLY_FIELDS = {"api_host", "api_port"}
SETTINGS_SECRET_FIELDS = {"telegram_bot_token", "api_auth_token"}
SETTINGS_SESSION_ONLY_FIELDS = {"incognito"}


def _settings_instance() -> Settings:
    return _gateway.settings if _gateway is not None else Settings()


@app.get("/api/settings", dependencies=[Depends(require_local_caller)])
def read_settings():
    settings = _settings_instance()
    values = {key: getattr(settings, key) for key in SETTINGS_EDITABLE_FIELDS | SETTINGS_READ_ONLY_FIELDS}
    # Never return stored credentials to the webview. An empty value means
    # "leave the existing secret unchanged" unless the user enters a new one.
    for key in SETTINGS_SECRET_FIELDS:
        values[key] = ""
    return values


@app.patch("/api/settings", dependencies=[Depends(require_local_caller)])
async def update_settings(request: Request):
    try:
        changes = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Request body must be a JSON object") from exc
    if not isinstance(changes, dict) or not changes:
        raise HTTPException(status_code=422, detail="Provide at least one setting to update")
    unknown = set(changes) - SETTINGS_EDITABLE_FIELDS
    if unknown:
        raise HTTPException(status_code=422, detail=f"Settings are read-only or unknown: {', '.join(sorted(unknown))}")

    settings = _settings_instance()
    numeric_bounds = {
        "model_context_length": (256, 131072), "temperature": (0, 2),
        "max_tokens": (1, 32768), "wake_word_threshold": (0, 1),
        "recording_timeout": (0.5, 300), "silence_threshold": (0, 1),
        "speech_rate": (0.25, 4), "screenshot_quality": (1, 100),
        "memory_top_k": (1, 100), "founder_mode_min_confidence_to_show": (0, 1),
    }
    allowed_values = {
        "tts_engine": {"kokoro", "piper", "system"},
        "whisper_device": {"auto", "cpu", "cuda", "mps"},
        "log_level": {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"},
    }
    for key, value in changes.items():
        current = getattr(settings, key)
        if key in SETTINGS_SECRET_FIELDS and value == "":
            continue
        if key == "assistant_name":
            try:
                validate_assistant_name(value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        elif isinstance(current, bool):
            if not isinstance(value, bool):
                raise HTTPException(status_code=422, detail=f"{key} must be a boolean")
        elif isinstance(current, int):
            if isinstance(value, bool) or not isinstance(value, int):
                raise HTTPException(status_code=422, detail=f"{key} must be an integer")
            if key in numeric_bounds and not numeric_bounds[key][0] <= value <= numeric_bounds[key][1]:
                raise HTTPException(status_code=422, detail=f"{key} must be between {numeric_bounds[key][0]} and {numeric_bounds[key][1]}")
        elif isinstance(current, float):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise HTTPException(status_code=422, detail=f"{key} must be a finite number")
            changes[key] = float(value)
            if key in numeric_bounds and not numeric_bounds[key][0] <= changes[key] <= numeric_bounds[key][1]:
                raise HTTPException(status_code=422, detail=f"{key} must be between {numeric_bounds[key][0]} and {numeric_bounds[key][1]}")
        elif current is None:
            if value is not None and not isinstance(value, str):
                raise HTTPException(status_code=422, detail=f"{key} must be text or null")
        elif not isinstance(value, str):
            raise HTTPException(status_code=422, detail=f"{key} must be text")
        if key in allowed_values and value not in allowed_values[key]:
            raise HTTPException(status_code=422, detail=f"{key} must be one of: {', '.join(sorted(allowed_values[key]))}")
        if isinstance(value, str) and len(value) > 2048:
            raise HTTPException(status_code=422, detail=f"{key} exceeds the maximum length of 2048 characters")
        if key == "ollama_host" and (not value.startswith(("http://", "https://")) or any(ch.isspace() for ch in value)):
            raise HTTPException(status_code=422, detail="ollama_host must be an http(s) URL without whitespace")

    applied = {key: value for key, value in changes.items()
               if key not in SETTINGS_SECRET_FIELDS or value != ""}
    persisted = {key: value for key, value in applied.items()
                 if key not in SETTINGS_SESSION_ONLY_FIELDS}
    try:
        if persisted:
            Settings.persist_overrides(persisted)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not save settings: {exc}") from exc
    for key, value in applied.items():
        setattr(settings, key, value)
    return read_settings()


@app.get("/api/environment", dependencies=[Depends(require_local_caller)])
def environment_report():
    """Credential-safe environment, setup, dependency, and capability view."""
    settings = _settings_instance()
    return EnvironmentCompatibilityManager().report({
        "ollama_host": settings.ollama_host,
        "primary_model": settings.primary_model,
        "fallback_model": settings.fallback_model,
        "embedding_model": settings.embedding_model,
        "vision_model": settings.vision_model,
    })


@app.post("/api/environment/repair", dependencies=[Depends(require_local_caller)])
def repair_environment(request: EnvironmentRepairRequest):
    """Install explicitly selected manifest groups into the active runtime."""
    groups = request.groups
    if not groups:
        raise HTTPException(status_code=422, detail="groups must be a non-empty list of dependency group names")
    try:
        return EnvironmentCompatibilityManager().repair_dependencies(groups)
    except Exception as exc:
        from runtime.compatibility import CompatibilityError
        if isinstance(exc, CompatibilityError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        logger.exception("Dependency repair failed")
        raise HTTPException(status_code=500, detail="Dependency repair failed; see local SAM logs") from exc


@app.on_event("startup")
def _startup():
    get_gateway()
    logger.info("iQOO phone gateway started")
    _start_connect_background_tasks()  # agent/cross-device: offline/timeout sweep


@app.on_event("shutdown")
def _shutdown():
    # Phase 3B, Checkpoint 3: this handler was previously missing entirely.
    # TaskGateway.shutdown() has existed since Phase 3A but had no caller
    # anywhere in the codebase (confirmed by a repo-wide grep during the
    # Checkpoint 1 audit) — the worker thread is daemon=True and was simply
    # killed on process exit, mid-task if one was running, with no chance
    # to persist state or exit cleanly. This wires the existing method up
    # so SIGTERM (sent by runtime.lifecycle.SAMRuntime.stop(), or Ctrl+C,
    # or anything else) actually reaches it via uvicorn's own shutdown
    # event, instead of being silently dropped as before.
    if _gateway is not None:
        _gateway.shutdown()
        logger.info("iQOO phone gateway shut down")
    _stop_connect_background_tasks()  # agent/cross-device


# ─── Task API ────────────────────────────────────────────────────────────

def require_task_auth(request: Request) -> None:
    """Enforces token authentication for task endpoints when api_auth_token is configured."""
    settings = _settings_instance()
    expected = (getattr(settings, "api_auth_token", "") or "").strip()
    if expected:
        token = request.headers.get("X-SAM-Token") or ""
        if not token:
            auth_header = request.headers.get("Authorization") or ""
            if auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
        import secrets
        if not token or not secrets.compare_digest(token, expected):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API authorization token",
            )


@app.post("/api/iqoo/tasks", response_model=TaskRecord, status_code=201, dependencies=[Depends(require_task_auth)])
def create_task(req: TaskCreateRequest):
    gateway = get_gateway()
    task_id = gateway.submit_task(
        instruction=req.instruction,
        input_type=req.input_type,
        attachments=[a.model_dump() for a in req.attachments],
    )
    return gateway.get_task(task_id)


@app.get("/api/iqoo/tasks/{task_id}", response_model=TaskRecord, dependencies=[Depends(require_task_auth)])
def get_task(task_id: str):
    record = get_gateway().get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


@app.post("/api/iqoo/tasks/{task_id}/cancel", response_model=TaskRecord, dependencies=[Depends(require_task_auth)])
def cancel_task(task_id: str):
    gateway = get_gateway()
    if gateway.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    gateway.cancel_task(task_id)
    return gateway.get_task(task_id)


@app.post("/api/iqoo/tasks/{task_id}/retry", response_model=TaskRecord, dependencies=[Depends(require_task_auth)])
def retry_task(task_id: str):
    gateway = get_gateway()
    try:
        new_id = gateway.retry_task(task_id)
    except TaskAlreadyActiveError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if new_id is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return gateway.get_task(new_id)


def _format_sse(event: dict) -> str:
    """Standard SSE framing, including `id:` — this is what makes the
    browser's native EventSource send a Last-Event-ID header
    automatically on reconnect, with zero client-side reconnect logic
    needed. See interfaces/api/events.py's module docstring for why this replaced
    Phase 1/2's single-consumer queue."""
    return f"id: {event['seq']}\ndata: {json.dumps(event)}\n\n"


async def event_stream(gateway: TaskGateway, task_id: str, after_seq: int,
                        request: "Request | None" = None) -> AsyncGenerator[str, None]:
    """The actual SSE generator, factored out of the endpoint so it can
    be exercised directly in tests without needing a live HTTP
    connection (request=None is valid for tests — the disconnect check
    is simply skipped, since there's no real client to disconnect).

    Phase 3A reconnect behavior: replays every event after `after_seq`
    first (0 replays the full history — what a phone reconnecting cold,
    e.g. after a browser refresh with no Last-Event-ID, needs to
    instantly recover current state including a possibly-already-reached
    terminal status), then continues with live events exactly as
    before. Never calls event_bus.cleanup() on disconnect anymore — that
    was the Phase 1/2 bug that made reconnect lose history.
    """
    seq = after_seq
    backlog = gateway.event_bus.get_since(task_id, seq)
    for event in backlog:
        seq = event["seq"]
        yield _format_sse(event)
        if event["phase"] in TERMINAL_STATUSES:
            return

    while True:
        if request is not None and await request.is_disconnected():
            logger.info(f"Client disconnected from event stream for {task_id}")
            return
        new_events = await asyncio.to_thread(gateway.event_bus.wait_for_new, task_id, seq, 1.0)
        if not new_events:
            # A reconnect that's already caught up to an already-terminal
            # task (e.g. Last-Event-ID == the latest seq, and that event
            # was the terminal one) has an empty backlog AND will never
            # see a new event — EventBus.publish refuses to append
            # anything after a terminal event, and the task genuinely
            # isn't running anymore. Without this check the generator
            # would heartbeat forever and never close. Caught by
            # tests/test_iqoo_phase3a_offline.py hanging indefinitely
            # before this fix — a real bug, not a hypothetical one.
            record = gateway.get_task(task_id)
            if record and record["status"] in TERMINAL_STATUSES:
                return
            yield ": heartbeat\n\n"
            continue
        for event in new_events:
            seq = event["seq"]
            yield _format_sse(event)
            if event["phase"] in TERMINAL_STATUSES:
                return


@app.get("/api/iqoo/tasks/{task_id}/events", dependencies=[Depends(require_task_auth)])
async def stream_events(task_id: str, request: Request):
    gateway = get_gateway()
    if gateway.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")

    last_event_id = request.headers.get("last-event-id")
    after_seq = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

    return StreamingResponse(
        event_stream(gateway, task_id, after_seq, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/iqoo/health", response_model=HealthStatus)
def health():
    return get_gateway().health()


@app.post("/api/iqoo/demo/reset", dependencies=[Depends(require_local_caller)])
def demo_reset():
    gateway = get_gateway()
    try:
        deleted = gateway.reset_demo_state()
    except DemoResetBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"reset": True, "tasks_cleared": deleted}


# ─── Brain / model selection ─────────────────────────────────────────────

@app.get("/api/models", response_model=BrainStatus)
def get_models():
    """Never a 5xx for an expected state: Ollama down, or no usable model
    installed, comes back as status="unavailable" with a detail (the same
    convention api/app.py's GET /api/model uses)."""
    return get_gateway().get_brain_status()


@app.post("/api/models/select", response_model=BrainStatus, dependencies=[Depends(require_local_caller)])
def select_model(req: ModelSelectRequest):
    """Each refusal has its own status so the UI can say exactly what to do:
    409 a task is running/queued, 404 not installed, 422 installed but not
    usable as a Brain, 502 Ollama couldn't describe the model, 503 Ollama
    unreachable, 500 the choice couldn't be saved (nothing was changed)."""
    try:
        return get_gateway().select_model(req.model)
    except BrainBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ModelNotInstalledError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ModelIncompatibleError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ModelMetadataError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except OllamaUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ModelManagerError as e:
        raise HTTPException(status_code=500, detail=str(e))


async def _next_from_sync_gen(gen):
    """Advance a requests-backed model-pull iterator off the event loop."""
    sentinel = object()
    result = await asyncio.to_thread(next, gen, sentinel)
    if result is sentinel:
        raise StopAsyncIteration
    return result


async def model_pull_stream(gateway: TaskGateway, name: str,
                            request: "Request | None" = None) -> AsyncGenerator[str, None]:
    """Relay Ollama NDJSON progress as the server's existing SSE format."""
    gen = gateway.model_manager.pull(name)
    seq = 0
    try:
        while True:
            if request is not None and await request.is_disconnected():
                logger.info("Client disconnected from model pull stream")
                return
            try:
                event = await _next_from_sync_gen(gen)
            except StopAsyncIteration:
                return
            seq += 1
            yield _format_sse({"seq": seq, "name": name, **event})
            if event.get("status") == "success":
                return
    except (OllamaUnavailableError, ModelPullError) as e:
        seq += 1
        yield _format_sse({"seq": seq, "name": name, "status": "error", "error": str(e)})
    finally:
        await asyncio.to_thread(gen.close)


@app.post("/api/models/pull", dependencies=[Depends(require_local_caller)])
async def pull_model(req: ModelPullRequest, request: Request):
    """Stream model-download progress. Restricted to loopback because the
    API binds to 0.0.0.0 by default and existing model routes lack user auth;
    pulling a model can consume substantial bandwidth and disk."""
    gateway = get_gateway()
    if gateway.get_brain_status().get("busy"):
        raise HTTPException(status_code=409, detail="Cannot pull a model while a task is active or queued.")
    return StreamingResponse(
        model_pull_stream(gateway, req.model, request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── Phone client (mounted last so it never shadows /api routes) ────────

if CLIENT_DIR.exists():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIR), html=True), name="client")


def main():
    import uvicorn
    from config.settings import Settings
    settings = Settings()
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()
