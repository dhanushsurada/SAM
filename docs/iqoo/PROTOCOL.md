# iQOO Branch — Protocol

## Endpoints (Phase 1)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/iqoo/tasks` | Submit a task |
| GET | `/api/iqoo/tasks/{task_id}` | Poll task status/result |
| GET | `/api/iqoo/tasks/{task_id}/events` | SSE execution progress stream |
| POST | `/api/iqoo/tasks/{task_id}/cancel` | Cancel a queued/running task |
| POST | `/api/iqoo/tasks/{task_id}/retry` | Resubmit as a fresh task |
| GET | `/api/iqoo/health` | Liveness, queue depth, brain reachability |

## Task creation

`POST /api/iqoo/tasks`

```json
{
  "instruction": "Turn this schema into a tested FastAPI backend",
  "input_type": "text",
  "attachments": []
}
```

`input_type`: one of `text | voice | image | image+text | image+voice`.
**Phase 1 executed `text` only.** Phase 2 adds real image/audio
processing for the other four — see `PERCEPTION.md` for the vision and
audio contracts, attachment shape, and MIME/size validation rules. Any
attachment that fails validation (bad MIME, malformed base64, oversized,
or missing for the declared `input_type`) is rejected with a `422` at
task-creation time, before a task row is even created.

Response (`201`):

```json
{
  "task_id": "uuid",
  "instruction": "...",
  "input_type": "text",
  "attachments": [],
  "status": "queued",
  "result_text": null,
  "error": null,
  "cancel_requested": false,
  "created_at": "...",
  "updated_at": "..."
}
```

Malformed requests (missing/empty `instruction`) get a standard FastAPI
`422` with field-level validation errors — no custom handling needed.

## Task states

```
queued → received → understanding → perceiving → planning → executing → verifying → completed
                        (text: skipped)                                            → failed
                                                                                    → cancelled
```

`perceiving` (Phase 2): only entered for `input_type != "text"`. Runs
`iqoo/gateway.py::_perceive` (vision/audio interpretation) before the
Brain ever sees the task. A `text` task skips straight from `received`
to `understanding`, identical to Phase 1.

`queued`: row created, not yet picked up by the worker thread.
`received`: PDR's first event, fired the instant the row is created —
in Phase 1 this is emitted immediately after `queued` since there is
no meaningful gap between the two yet (a longer queue in Phase 3's
higher-concurrency testing may separate them further).

`testing` is defined in the PDR's full state list but not yet emitted by
anything in Phase 1 or 2 — see `ARCHITECTURE.md`'s "what's deliberately
not done yet."

## Execution events (SSE)

`GET /api/iqoo/tasks/{task_id}/events` — `text/event-stream`. Each
message:

```json
{
  "type": "execution.step",
  "task_id": "uuid",
  "phase": "executing",
  "message": "Step 1: control",
  "timestamp": "..."
}
```

The stream closes after a terminal-phase event (`completed`, `failed`,
`cancelled`) or when the client disconnects. Heartbeat comment lines
(`: heartbeat\n\n`) are sent during idle gaps so intermediate proxies
(including Office Kit's mirrored connection) don't time the connection
out.

## Cancellation

`POST /api/iqoo/tasks/{task_id}/cancel` sets a real `threading.Event`
that `react_loop.run_planned_task`/`run_task` check between every step —
the same mechanism `main.py` already uses for "stop it" (see that file's
`_cancel_event`), not a UI-only flag. A queued-but-not-yet-started task
is cancelled before the Brain is ever called.

## Retry

`POST /api/iqoo/tasks/{task_id}/retry` re-submits the original
instruction as a **new** `task_id`. It does not resume mid-plan — that
needs step-level checkpointing, which is Phase 3 (task recovery) scope.

## Health

```json
{
  "status": "ok",
  "brain_reachable": true,
  "active_task": "uuid-or-null",
  "queue_depth": 0,
  "version": "iqoo-phase1"
}
```

`brain_reachable` calls the existing `Brain._check_ollama()` — not
duplicated, just surfaced.
