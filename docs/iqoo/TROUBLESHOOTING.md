# iQOO Branch — Troubleshooting

## Server won't start

- `ModuleNotFoundError: fastapi` / `uvicorn` — `pip install -r requirements.txt`
  (they were added in this branch, see the iQOO section at the bottom of
  the file).
- Port 8420 already in use — another `iqoo/server.py` instance is
  probably still running from a previous demo; kill it or change the
  port in `iqoo/server.py::main()`.

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

There is no task-level timeout in Phase 1 (see `TEST_PLAN.md` known
gaps). If the underlying Brain/Ollama call hangs, the task will not
self-recover — restart `iqoo/server.py`. Phase 3 adds timeout handling.

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
