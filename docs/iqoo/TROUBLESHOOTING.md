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

Expected in Phase 1. `input_type != "text"` fails on purpose with a
message naming Phase 2 — see `PROTOCOL.md`. This is not a bug to fix;
it's the honest boundary of what's built so far.

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
passing unchanged (`TEST_PLAN.md`). If one fails, it's most likely
environment drift (missing dependency, stale `~/.sam_data`) rather than
something this branch touched — the only non-`iqoo/`/`client/`/`tests/`/
`docs/` file changed is the additive `on_event` parameter in
`agent/react_loop.py`, which defaults to `None` and changes no existing
behavior when omitted.
