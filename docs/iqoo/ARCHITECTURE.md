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

## Phase 2 addition: perception adapters

`iqoo/vision_adapter.py` and `iqoo/audio_adapter.py` slot into
`iqoo/gateway.py::_perceive`, called before `brain.process()` for any
non-`text` task. See `PERCEPTION.md` for the full design, including the
documented coupling in `AudioAdapter` (reaches into
`ears/stt.py::SpeechToText`'s private `_load_model()`/`_model` rather
than a new public method, specifically to avoid touching a file outside
`iqoo/`/`client/`/`tests/`/`docs/iqoo/` without stopping to justify it
first — flagged as a recommended fast-follow, not hidden).

## Data separation

`iqoo/task_store.py` (`~/.sam_data/iqoo/tasks.db`) holds competition task
bookkeeping only — instruction text, status, timestamps, result/error.
It does not touch `memory/store.py` (ChromaDB + episodic SQLite) or
`founder_mode`'s store. This mirrors the "Local Data Separation"
principle already used by `ecosystem/device_registry.py`: task
bookkeeping is operational metadata, not AI memory, even though both
live under `~/.sam_data`.

## What's deliberately not done yet

- No demo reset / hackathon mode (Phase 3 scope).
- No reconnect/session-recovery beyond what SQLite status + a fresh SSE
  subscription already gives you (Phase 3 scope).
- No task-level timeout (Phase 3 scope).
- Phone client UI for camera/audio capture-and-submit and the
  perception progress states — code was written in this phase (see
  `PROGRESS.md`) but has not been exercised against a real device.

## Phase 3A: reliability & recovery

**[IMPLEMENTED, TESTED OFFLINE — see `tests/test_iqoo_phase3a_offline.py`, 44/44]**

### SSE reconnect — the actual fix

Phase 1/2 kept a single `queue.Queue` per task, destructively drained by
whichever connection read it, and `event_bus.cleanup()` was called the
moment ANY stream disconnected. A reconnecting phone (dropped WiFi,
browser refresh, backgrounded tab) got either a queue with nothing left
in it, or no queue at all — silently losing the terminal event. This was
the real bug, not a hypothetical one.

`iqoo/events.py` now keeps a full ordered, sequence-numbered history per
task instead. `iqoo/server.py`'s `/api/iqoo/tasks/{id}/events` reads the
standard SSE `Last-Event-ID` header (which browsers send automatically
on reconnect — zero client-side reconnect logic needed) and replays
every event after that point before continuing live. A cold reconnect
(`Last-Event-ID` absent) replays the full history, including an
already-reached terminal status. History is never deleted on disconnect
— only by an explicit demo reset.

Found and fixed a genuine hang while building this: a reconnect that's
already fully caught up to an already-terminal task (empty backlog, and
no future event will ever come) would loop on `wait_for_new(...)`
forever with only heartbeats, since nothing was checking "is this task
actually already done" in that branch. Fixed by re-checking task status
on every empty wait before looping again.

### Timeout — an honest trade-off, not a silent gap

`TaskGateway._run_task_with_timeout` runs `_process_task` on a nested
thread with a hard wall-clock ceiling (`task_timeout_seconds`, default
600s). If it doesn't finish in time, the phone is told "failed (timed
out)" immediately. **But** nothing in Python can forcibly kill a thread
blocked inside a synchronous Hands call or an unbounded network
request — the only real way is killing the process. So the FIFO worker
thread still waits for the orphaned thread to actually finish before
touching Hands again, preserving the single-flight invariant at the
cost of the queue not *instantly* continuing after a true hang. This is
documented, not hidden — see the docstring on that method.

A companion guard was needed and added: once a task reaches a terminal
status, `TaskStore.update_status`/`EventBus.publish` refuse any further
write for that task_id. Without this, an orphaned thread that
eventually finishes late (after the phone was already told "timed out")
could silently flip the status back to "completed" minutes later.

### Worker recovery — a real gap found and fixed during testing

Moving `_process_task` onto a nested thread for the timeout watchdog
initially dropped the exception handling that used to wrap it directly
in `_worker_loop` — an exception raised *outside* `_process_task`'s own
inner try/except (e.g. in the pre-perceive cancellation check) would
propagate out of the nested thread silently (Python swallows uncaught
thread exceptions rather than crashing the process), leaving that task
stuck in a non-terminal status forever and never actually testing the
"task A fails, task B still executes" requirement. Caught by
`test_worker_recovery_task_a_fails_task_b_still_executes` before it
shipped — fixed by adding an explicit catch-all in the nested thread's
target function.

### Retry safety

`retry_task` now rejects retrying a task that hasn't reached a terminal
status (`TaskAlreadyActiveError` → HTTP 409) — retrying a still-running
task would create two competing attempts at the same instruction with
no clear "which one is real." A new `retried_from` column links a retry
back to its origin for debugging history. Fresh cancel-state per retry
was already correct in Phase 1/2 (new task_id → new `threading.Event`)
and is now explicitly tested rather than just assumed.

### Server-restart recovery

`TaskStore.recover_orphaned_tasks()` runs once at `TaskGateway.__init__`:
any task left in a non-terminal status by a previous process (crash,
kill, restart mid-task) is marked `failed` with a distinguishable
`"Orphaned by a server restart..."` message. Tested by directly
manipulating the SQLite DB and constructing a fresh `TaskStore` instance
against the same file (a real process restart was not performed — see
`PROGRESS.md`'s hardware/real-environment validation status).

### Demo reset

`TaskGateway.reset_demo_state()` (→ `POST /api/iqoo/demo/reset`) deletes
every task row and all event history. Refuses with `DemoResetBusyError`
(→ 409) while a task is active or queued, so a reset can never be issued
out from under running work. Statically verified via AST inspection
(not just behavior) that neither `TaskStore.reset_demo_state` nor
`EventBus.reset_all` import or reference `memory`/`founder_mode` in
their actual code — SAM's real long-term memory cannot be touched by
this call no matter what invokes it.

### Health diagnostics

`health()` now also reports `worker_alive`, `vision_model_available`
(via a cheap Ollama `/api/tags` check, `None` if Ollama itself is
unreachable — distinct from "reachable but model missing" = `False`),
`whisper_available` (whether `faster-whisper` is importable, no model
loaded), and `uptime_seconds`. `status` becomes `"degraded"` if the
worker has died or the brain is unreachable. No task instructions,
attachment content, or other user data is included.
