# iQOO Branch — Architecture

## Diagram (Phase 1 as built)

```
REAL WORLD
   │ text (voice/camera entry points exist, not yet wired to execution)
   ▼
PHONE CLIENT (client/, vanilla JS)
   │ HTTP POST / SSE GET  (same-WiFi today; Office Kit-compatible — see OFFICE_KIT.md)
   ▼
iqoo/server.py  (FastAPI — standalone process, does NOT touch main.py)
   │
   ▼
iqoo/gateway.py  (TaskGateway — thin adapter, one worker thread)
   │  constructs, exactly like ecosystem/telegram_bridge.py:
   │  Identity · MemoryRetriever · FounderModeManager · Brain · ReactLoop
   ▼
core/brain.py (Brain.process)  →  agent/react_loop.py (run_planned_task)
   │                                  │
   │                                  ├── agent/planner.py (decompose)
   │                                  ├── agent/verifier.py (verify/decide)
   │                                  ├── agent/reflection.py (reflect)
   │                                  └── hands/ (control · browser · terminal · vision)
   ▼
iqoo/task_store.py (status persisted)  +  iqoo/events.py (progress published)
   ▼
PHONE CLIENT (renders phase checklist + result)
```

## Why a standalone process, not main.py integration

`main.py`'s `SAM` class owns the wake-word/text-input loop and a single
`_process_lock`. `ecosystem/telegram_bridge.py` already established the
precedent of NOT reusing that class headlessly — it builds its own
Identity/Memory/FounderMode/Brain/ReactLoop instances and runs as a
separate process. `iqoo/server.py` follows the exact same precedent.
This means:

- `main.py` is untouched by this entire branch.
- The competition demo can run with or without the voice/text loop
  running at the same time.
- If this branch is ever deleted, nothing about core SAM changes.

## Why one worker thread, not asyncio-native execution

`ReactLoop` and the Hands (`hands/control`, `hands/browser`,
`hands/terminal`, `hands/vision`) are synchronous and were built under
the standing assumption that only one task runs at a time — this is
already enforced by `main.py`'s `_process_lock` and Telegram's
`asyncio.Lock`. `TaskGateway` holds the same invariant: a single
dedicated thread drains a FIFO `queue.Queue` of task_ids, so two phone
submissions can never race inside the same browser/vision session.
Submitting while a task is running just queues behind it (status stays
`queued`), exactly like main.py printing "still working on your previous
request."

## Why SSE, not WebSocket

PDR 8.5 allows either. SSE was chosen because:

- Progress only flows server → phone (no benefit to bidirectional).
- `EventSource` auto-reconnects on transient drops for free — useful
  over Office Kit's mirrored link or a flaky hotspot.
- Zero extra dependency (Starlette/FastAPI already support streaming
  responses; WebSocket support would need the `websockets` package).

## The `on_event` hook in `agent/react_loop.py`

The only change to existing orchestration code in this entire branch is
one additive, optional `on_event: Callable[[phase, message], None] = None`
parameter on `run_task` and `run_planned_task`, fired at plan creation,
before/after each step's verified execution, and on stagnation abort.
Default `None` means `main.py` and `telegram_bridge.py` are completely
unaffected — this mirrors exactly how `cancel_event` was added in an
earlier phase (see the existing docstrings in that file). Without this,
the phone would only ever see `understanding` → `completed`, with no
visibility into planning/execution/verification — the granularity the
PDR's event contract actually asks for.

## Data separation

`iqoo/task_store.py` (`~/.sam_data/iqoo/tasks.db`) holds competition task
bookkeeping only — instruction text, status, timestamps, result/error.
It does not touch `memory/store.py` (ChromaDB + episodic SQLite) or
`founder_mode`'s store. This mirrors the "Local Data Separation"
principle already used by `ecosystem/device_registry.py`: task
bookkeeping is operational metadata, not AI memory, even though both
live under `~/.sam_data`.

## What Phase 1 deliberately does not do

- No image/voice attachment processing (fails honestly — see
  `PROGRESS.md`).
- No granular "testing" phase distinct from "executing" (a terminal
  action running `pytest` still reports as `executing`/`verifying` in
  Phase 1; Phase 2's `skills/iqoo/whiteboard_to_backend/` workflow will
  emit an explicit `testing` phase).
- No demo reset / hackathon mode (Phase 3 scope).
- No reconnect/session-recovery beyond what SQLite status + a fresh SSE
  subscription already gives you (Phase 3 scope).
