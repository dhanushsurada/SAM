"""
iQOO — Phone Task Gateway Server (Phase 1)

Standalone process, same philosophy as ecosystem/telegram_bridge.py: it
does NOT run inside main.py's voice/text loop, and main.py is completely
untouched by this branch. Run it alongside (or instead of) SAM's voice
loop:

    python -m iqoo.server

Serves:
- POST   /api/iqoo/tasks                submit a task
- GET    /api/iqoo/tasks/{id}           poll task status
- GET    /api/iqoo/tasks/{id}/events    SSE execution progress stream
- POST   /api/iqoo/tasks/{id}/cancel    cancel a running/queued task
- POST   /api/iqoo/tasks/{id}/retry     resubmit as a fresh task
- GET    /api/iqoo/health               liveness + queue/brain status
- /                                     the phone client (client/)
"""

import asyncio
import json
import logging
import queue as queue_mod
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from iqoo.gateway import TaskGateway
from iqoo.task_store import TERMINAL_STATUSES
from iqoo.schemas import TaskCreateRequest, TaskRecord, HealthStatus

logger = logging.getLogger("SAM.iQOO.Server")

BASE_DIR = Path(__file__).parent.parent
CLIENT_DIR = BASE_DIR / "client"

app = FastAPI(title="SAM iQOO Phone Gateway", version="iqoo-phase1")

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
    new_id = gateway.retry_task(task_id)
    if new_id is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return gateway.get_task(new_id)


@app.get("/api/iqoo/tasks/{task_id}/events")
async def stream_events(task_id: str, request: Request):
    gateway = get_gateway()
    if gateway.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")

    q = gateway.event_bus.subscribe_queue(task_id)

    async def event_stream():
        try:
            while True:
                if await request.is_disconnected():
                    logger.info(f"Client disconnected from event stream for {task_id}")
                    break
                try:
                    event = await asyncio.to_thread(q.get, True, 1.0)
                except queue_mod.Empty:
                    record = gateway.get_task(task_id)
                    if record and record["status"] in TERMINAL_STATUSES:
                        break
                    yield ": heartbeat\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
                if event.get("phase") in TERMINAL_STATUSES:
                    break
        finally:
            gateway.event_bus.cleanup(task_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/iqoo/health", response_model=HealthStatus)
def health():
    return get_gateway().health()


# ─── Phone client (mounted last so it never shadows /api routes) ────────

if CLIENT_DIR.exists():
    app.mount("/", StaticFiles(directory=str(CLIENT_DIR), html=True), name="client")


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO,
                         format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=8420)


if __name__ == "__main__":
    main()
