"""
SAM API Interface — the phone-task HTTP + SSE gateway.

    task_store.py   SQLite-backed task ledger
    events.py       Thread-safe, reconnect-safe SSE event bus
    schemas.py      Pydantic request/response contract
    gateway.py      TaskGateway — wires HTTP requests to SAM Core
    server.py       FastAPI app and routes (mounts interfaces/web/ as static files)

Formerly iqoo/{task_store,events,schemas,gateway,server}.py, relocated in
Phase 3A.5. See docs/iqoo/PHASE_3A5_MIGRATION.md.
"""
