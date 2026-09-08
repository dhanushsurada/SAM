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
- /                                     the phone client (interfaces/web/)
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from interfaces.api.gateway import TaskGateway, TaskAlreadyActiveError, DemoResetBusyError
from interfaces.api.task_store import TERMINAL_STATUSES
from interfaces.api.schemas import TaskCreateRequest, TaskRecord, HealthStatus

logger = logging.getLogger("SAM.iQOO.Server")

# interfaces/api/server.py -> interfaces/api -> interfaces -> repo root.
# (One level deeper than the old iqoo/server.py -> iqoo -> repo root, since
# this file now lives one directory deeper.)
BASE_DIR = Path(__file__).parent.parent.parent
CLIENT_DIR = BASE_DIR / "interfaces" / "web"

app = FastAPI(title="SAM iQOO Phone Gateway", version="iqoo-phase3a")

_gateway: TaskGateway = None  # constructed lazily on first request / at startup


def get_gateway() -> TaskGateway:
    global _gateway
    if _gateway is None:
        _gateway = TaskGateway()
    return _gateway


@app.on_event("startup")
def _startup():
    get_gateway()
    logger.info("iQOO phone gateway started")


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


# ─── Task API ────────────────────────────────────────────────────────────

@app.post("/api/iqoo/tasks", response_model=TaskRecord, status_code=201)
def create_task(req: TaskCreateRequest):
    gateway = get_gateway()
    task_id = gateway.submit_task(
        instruction=req.instruction,
        input_type=req.input_type,
        attachments=[a.model_dump() for a in req.attachments],
    )
    return gateway.get_task(task_id)


@app.get("/api/iqoo/tasks/{task_id}", response_model=TaskRecord)
def get_task(task_id: str):
    record = get_gateway().get_task(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return record


@app.post("/api/iqoo/tasks/{task_id}/cancel", response_model=TaskRecord)
def cancel_task(task_id: str):
    gateway = get_gateway()
    if gateway.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    gateway.cancel_task(task_id)
    return gateway.get_task(task_id)


@app.post("/api/iqoo/tasks/{task_id}/retry", response_model=TaskRecord)
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


@app.get("/api/iqoo/tasks/{task_id}/events")
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


@app.post("/api/iqoo/demo/reset")
def demo_reset():
    gateway = get_gateway()
    try:
        deleted = gateway.reset_demo_state()
    except DemoResetBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"reset": True, "tasks_cleared": deleted}


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
