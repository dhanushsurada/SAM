# iQOO Branch — Troubleshooting

## Server won't start

- `ModuleNotFoundError: fastapi` / `uvicorn` — `pip install -r requirements.txt`
  (they were added in this branch, see the iQOO section at the bottom of
  the file).
- Port 8420 already in use — another SAM API server instance (started via
  `sam start api`, `python -m interfaces.api.server`, or the legacy
  `python -m iqoo.server` shim — they're the same process) is probably
  still running from a previous demo; kill it (`sam stop api` if it was
  started that way) or change `api_port` in `config/settings.py`, the
  single source of truth for the port everywhere (server bind, `sam
  doctor`'s check, and `runtime`'s health URL all read it from there).

## Phone can't reach the server

- Confirm the phone and laptop are on the same WiFi (Phase 1 has no
  Office Kit integration tested yet — see `OFFICE_KIT.md`).
- Confirm the laptop's firewall allows inbound connections on 8420.
- Use the laptop's actual LAN IP, not `localhost`/`127.0.0.1`, in the
  phone's browser URL.

## `brain_reachable: false` on `/api/iqoo/health`

Ollama isn't running or isn't reachable at `settings.ollama_host`. Start
it the same way you would for `main.py` — this branch didn't change
anything about how SAM talks to Ollama.

## A task submitted with a photo always fails

**Phase 1 behavior (no longer applies as of Phase 2).** Phase 2 actually
processes `image`/`voice`/`image+text`/`image+voice` tasks. If one still
fails, check the task's `error` field first — perception failures are
reported with a specific reason (e.g. "Vision model unreachable",
"Unsupported image MIME type", "Transcription produced no text"), not a
generic message. See `PERCEPTION.md` for the full contract.

## `422` on task creation with an attachment

Check the specific validation error in the response body — it names
exactly which rule failed: unsupported MIME type, malformed base64,
oversized payload, or a missing attachment for the declared
`input_type`. See `PERCEPTION.md`'s validation section.

## Voice/image task fails with a fallback-related message

If the error mentions "No faster-whisper installed" — the fallback
`speech_recognition` path only accepts WAV/AIFF/FLAC, and phone browsers
almost always record webm/ogg/mp4. Install faster-whisper for real
format support; this is a documented, honest limitation, not a bug (see
`PERCEPTION.md`).

## Task stuck in `executing` forever

**Phase 3A note:** there is now a hard task timeout (default 600s) —
a stuck task self-reports `failed` with a `"timed out after ...s"`
message and an SSE `failed` event, so it should never actually stay
stuck indefinitely from the phone's perspective. It CAN still occupy
the worker thread longer than the timeout, though — see
`ARCHITECTURE.md`'s honest trade-off explanation. If a restart happens
while a task is non-terminal, `recover_orphaned_tasks()` marks it
`failed` on the next startup rather than leaving it stuck forever.

## Retrying a task returns 409

**Phase 3A:** retry is only allowed once the original task has reached
a terminal status. If you get a 409, the task is still running —
cancel it first, or wait for it to finish, then retry.

## `POST /api/iqoo/demo/reset` returns 409

A task is currently active or still queued. Cancel it or wait for it to
finish, then reset again. This guard exists specifically so a reset can
never corrupt a task that's actually running.

## SSE reconnects but shows old events again / never closes

**Phase 3A fixed both of these as real, found bugs** (not hypothetical
edge cases — both caused actual test hangs/failures during
development, documented in `TEST_PLAN.md`):
- A reconnect that's already caught up to an already-terminal task now
  closes immediately instead of heartbeating forever.
- Reconnecting with a `Last-Event-ID` you've already seen returns zero
  duplicate events — the browser's native `EventSource` sends this
  header automatically, no client code needed.

If you still see this, check that any custom SSE client (not
`EventSource`) is actually sending `Last-Event-ID` on reconnect.

## SSE stream never emits anything

- Check `/api/iqoo/tasks/{task_id}` directly first — if `status` is
  already terminal, the events queue may have been drained/cleaned up
  before the phone subscribed (a re-subscribe after a task already
  finished sees nothing new, since there's no event backlog/replay yet —
  Phase 3 gap). The task's final result is still on the `GET` endpoint.
- If status is stuck at `queued`, another task is currently occupying the
  single worker thread — check `queue_depth` on `/api/iqoo/health`.

## Two tasks submitted close together seem to "block" each other

This is intentional, not a bug: SAM's Hands aren't safe for concurrent
execution (see `ARCHITECTURE.md`). The second task queues and starts
only after the first finishes.

## Existing SAM tests fail after pulling this branch

They shouldn't — all 12 pre-existing offline suites were verified
passing unchanged (`TEST_PLAN.md`, re-verified again in Phase 2). If one
fails, it's most likely environment drift (missing dependency, stale
`~/.sam_data`) rather than something this branch touched — this branch's
only non-`iqoo/`/`client/`/`tests/`/`docs/` file change, in either
phase, is the additive `on_event` parameter in `agent/react_loop.py`,
which defaults to `None` and changes no existing behavior when omitted.

## `test_feature_tier_offline.py` fails on Termux (Python 3.13 / cryptography)

This is a pre-existing environment limitation unrelated to iQOO: on
Android Termux with Python 3.13.13 + cryptography 50.0.0, the native
`_rust.abi3.so` extension fails to resolve `PyBaseObject_Type`. It
reproduces identically with iQOO absent entirely. Do not modify
`licensing/` or the cryptography dependency to work around it — the fix
is an environment/toolchain issue (e.g. a different cryptography
version compatible with that Python build), not a code change here.
