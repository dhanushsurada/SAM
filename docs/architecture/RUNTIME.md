# SAM Runtime — Architecture

Phase 3B, Checkpoint 7. Covers `runtime/` as actually built (Checkpoints 3–5),
not the full Section 5–13 vision — where the two differ, that's called out
explicitly below rather than glossed over.

Does not touch or supersede `docs/iqoo/PHASE_3A5_MIGRATION.md`, which remains
the historical record of the prior phase.

---

## 1. Scope and boundary

`runtime` manages *whether* SAM's processes are running — start, stop,
restart, status, health. It does not implement reasoning, planning, memory,
or verification (that's `core`/`agent`/`memory`/`founder_mode`), and it is
not coupled to vivo/iQOO, Telegram, or the web UI specifically — those are
just three `ProcessSpec`s it happens to know about
(`runtime.lifecycle.specs.default_specs`).

```
runtime/
├── __init__.py           re-exports SAMRuntime, RuntimeStatus, ProcessSpec, default_specs
├── lifecycle/
│   ├── specs.py           ProcessSpec — how to launch each process, how to tell it's ready
│   ├── state.py           PID/state-file bookkeeping, cross-platform liveness checks
│   └── manager.py         SAMRuntime — the facade: start/stop/restart/status/health
└── health/
    └── status.py          RuntimeStatus enum, compute_status()/compute_health()
```

`runtime/lifecycle/__init__.py` deliberately does **not** re-export
`manager.py` — `manager.py` depends on `runtime.health.status`, which depends
on `runtime.lifecycle.specs`/`state`. Eagerly importing `manager` from the
package `__init__` created a real circular import (hit and fixed during
Checkpoint 4). Get `SAMRuntime` from `runtime` (top-level) or
`runtime.lifecycle.manager` directly.

## 2. The three processes, and why they're not interchangeable

Confirmed by direct reading of each file (Checkpoint 1 audit), not assumed:

| | `main.py` (voice) | `interfaces/api/server.py` (api) | `interfaces/telegram/telegram_bridge.py` (telegram) |
|---|---|---|---|
| Launch | `python main.py` | `python -m interfaces.api.server` | `python -m interfaces.telegram.telegram_bridge` |
| Health endpoint | none | `GET /api/iqoo/health` | none |
| Own signal handling | yes (SIGINT/SIGTERM) | no (relies on uvicorn's default + our new shutdown hook) | yes, but via `python-telegram-bot`'s own internals, not SAM's code |
| Optional-dependency behavior | — | vision/whisper unavailable → `degraded`, not fatal | no `telegram_bot_token` → raises immediately, before polling starts |

Because two of the three expose nothing queryable, `runtime` uses two
different readiness strategies (`ProcessSpec.ready_check`):

- **`"http"`** (api only): poll the real health endpoint until it responds
  or the process exits or the timeout elapses.
- **`"alive_after_grace"`** (voice, telegram): sleep a short grace period,
  then check the process didn't exit. This is honestly weaker — it proves
  "didn't crash immediately," not "is actually working" — and `runtime`
  never claims otherwise in its own messages or health output.

## 3. Lifecycle (Checkpoint 3)

One JSON state file per process at `~/.sam_data/runtime/<name>.json`:
`{name, pid, command, started_at, phase, message}`.

**Why `~/.sam_data/`, against Section 7's default lean:** every other piece
of SAM's persistent state already lives there
(`~/.sam_data/iqoo/tasks.db`, `~/.sam_data/ecosystem/devices.db`,
`~/.sam_data/settings.yaml`). Putting runtime state anywhere else would be
the one exception to an otherwise uniform convention — so it gets its own
subfolder there instead, which satisfies "clearly separated" without also
being the odd one out.

**`start()`**: refuses to double-spawn if already running (checked via pid
liveness *and* a command-line identity check, see below); writes
`phase="starting"` immediately; waits for readiness; on success moves to
`phase="ready"`; on failure or timeout, terminates the process it just
spawned (there's no PID-reuse ambiguity for a process spawned in the same
call) and records `phase="failed"` with the failure output, rather than
silently reverting to indistinguishable-from-never-tried.

**`stop()`**: marks `phase="stopping"` before signaling (so a concurrent
`status()` call sees it), sends SIGTERM, polls for actual death, escalates
to SIGKILL after `shutdown_timeout_seconds`. **Windows note:** `os.kill(pid,
SIGTERM)` on Windows maps to `TerminateProcess` — there is no POSIX-style
graceful signal delivery to an arbitrary external process there. The
"graceful" and "escalated" code paths are therefore not actually different
in kind on Windows, and this is stated plainly rather than implying a parity
that doesn't exist.

**PID-reuse safety**: before ever signaling a pid read back from a state
file, `pid_matches_expected()` checks that the *current* process at that pid
still has the expected command-line fragment (e.g. `"interfaces.api.server"`).
If it doesn't match, `stop()` refuses and explains why rather than signaling
an unrelated process. This is a sanity check, not a security boundary — it
fails open (permits the operation) if the command line can't be determined
at all, rather than blocking a legitimate stop on a platform quirk.

**Zombie reaping**: `is_pid_alive()` opportunistically reaps via
`waitpid(WNOHANG)` before checking `kill(pid, 0)`. Without this, a process
`SAMRuntime` is the literal OS parent of (which `restart()` always is, since
it calls `stop()` then `start()` in one process) looks "still alive" after
being signaled, because a signaled-but-unreaped child is a zombie that still
responds to `kill(pid, 0)`. Found by running the tests, not by inspection —
see `test_runtime_lifecycle_offline.py`'s restart checks.

## 4. Status and health (Checkpoint 4)

```python
class RuntimeStatus(str, Enum):
    STOPPED, STARTING, READY, DEGRADED, FAILED, STOPPING
```

Computed fresh on every call from the state file plus (for `api`) a live
poll of the real health endpoint — never cached:

| phase in state file | pid alive & matches | api health says | → |
|---|---|---|---|
| *(no state file)* | — | — | `STOPPED` |
| `failed` | — | — | `FAILED` (persists until next `start()`) |
| `starting` | yes | — | `STARTING` |
| `starting` | no | — | `FAILED` (died before confirming ready) |
| `stopping` | yes | — | `STOPPING` |
| `stopping` | no | — | `STOPPED` |
| `ready` | no | — | `STOPPED` |
| `ready` (http) | yes | `"ok"` | `READY` |
| `ready` (http) | yes | not `"ok"` or unreachable | `DEGRADED` |
| `ready` (alive_after_grace) | yes | *(no endpoint exists)* | `READY` |

**Health reuses, not duplicates, the existing Phase 3A health dict.**
`TaskGateway.health()` already treats `vision_model_available` and
`whisper_available` as informational — they don't affect its own
`ok`/`degraded` computation. `compute_health()` for the api process merges
that live dict straight in under `gateway_health` rather than re-deriving
any of it. Confirmed live against the real gateway during Checkpoint 5 (see
§7) — `sam status` correctly reported `DEGRADED` because `brain_reachable`
was false with no Ollama running, exactly the existing semantics.

For voice/telegram, `health()` never fabricates a `gateway_health`-shaped
dict that doesn't exist — it returns `process_alive`/`uptime_seconds` and an
explicit `note` explaining the limitation.

## 5. `sam doctor` (Checkpoint 5 — a foundation, not the full Section 13 list)

Implemented: Python version, config loads, `~/.sam_data` writable (real
write-test), five dependency import checks (explicitly labeled as import
checks, not functionality checks — Section 13's own distinction), Ollama
reachability via a live request (not just "is it installed"), port 8420
free-or-ours, all three processes' `RuntimeStatus`, Telegram token presence
(WARN, not FAIL — it's optional).

Explicitly not implemented, and shown as `UNVERIFIED` rather than faked:
whether vision/STT/TTS model *weights* are actually downloaded (only
library imports are checked), and OS-level permission grants (mic, camera,
accessibility) — not checkable from a CLI process at all, on any platform.

## 6. Known gaps against the full Section 5–19 vision

Stated plainly rather than left for someone to discover later:

- ~~Configuration is not yet centralized into `config/settings.py`~~
  **Resolved (post-Checkpoint-7):** `Settings().api_host` / `.api_port`
  (default unchanged: `0.0.0.0:8420`) are now the single source of truth.
  `interfaces/api/server.py`'s `main()`, `runtime/lifecycle/specs.py`'s
  `default_specs()` (health_url), and `sam_cli.py`'s `doctor` port-free
  check all read the same `Settings()` value — see
  `tests/test_runtime_config_offline.py`. Scope note: this closes Section
  16 for host/port specifically. `ProcessSpec`'s startup/shutdown timeouts
  are still Python-level defaults in `specs.py`, not yet in `Settings`.
- **Voice and Telegram were never started/stopped for real** by this code —
  only the api process was (§7). Telegram is additionally blocked in *this*
  development sandbox specifically by network policy (no route to Telegram's
  API), not just missing dependencies; that constraint may not apply to a
  real deployment.
- **Windows's `tasklist`/`taskkill` paths have never run on real Windows** —
  only implemented by pattern-matching `config/settings.py`'s existing
  `sysctl`/`wmic` platform branches.
- **`runtime/permissions/` and `runtime/events/`** (Section 5's proposed
  structure) were never created — no concrete responsibility justified them
  during Checkpoints 3–5, per Section 5's own "don't create fake modules."

## 7. What's actually been verified, and how

| Layer | Method | Result |
|---|---|---|
| `runtime.lifecycle` | offline suite against throwaway dummy processes | 32/32 |
| `runtime.health` | offline suite against dummies + hand-written state, incl. concurrent STARTING/STOPPING observation via a real background thread | 22/22 |
| `sam_cli.py` integration | offline suite: every subcommand survives dispatch (subprocess, real CLI) + fake-runtime output checks | 31/31 |
| **The real `interfaces/api/server.py`** | manual, live, via the actual CLI: start → real pid → `sam status` polled the real health endpoint and got a genuine `DEGRADED` → graceful stop (proving the Checkpoint 3 shutdown-hook fix fires against a real process, not a test double) → restart across separate process invocations → confirmed genuinely different pids | pass, see `docs/deployment/LOCAL_RUNTIME.md` for the transcript |
| Full existing regression (Phases 1–3A.5) | every offline suite re-run after each checkpoint | 388+ checks, zero regressions, at every checkpoint |

Total offline checks introduced by Phase 3B so far: 85 (32+22+31), on top of
the pre-existing ~398+ baseline, all passing.
