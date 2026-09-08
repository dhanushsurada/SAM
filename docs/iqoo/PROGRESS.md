# iQOO Branch — Progress

Status labels used throughout, per the Phase 3 protocol:
**IMPLEMENTED** · **TESTED OFFLINE** · **REAL-PROCESS TESTED** ·
**REAL-DEVICE TESTED** · **HARDWARE VERIFIED** · **UNVERIFIED** · **DEFERRED**

(REAL-PROCESS TESTED added at Phase 3B: a real local OS process was
started/stopped/polled — meaningfully more than an offline mock, but
NOT the same claim as REAL-DEVICE TESTED, which means actual iQOO/vivo
hardware. The two are never collapsed into each other.)

**PHASE 1:** COMPLETE
**PHASE 2:** COMPLETE
**PHASE 3A (Reliability & Recovery):** COMPLETE — IMPLEMENTED, TESTED OFFLINE.
**PHASE 3A.5 (Migration to canonical SAM architecture):** COMPLETE — IMPLEMENTED, TESTED OFFLINE. See `PHASE_3A5_MIGRATION.md`.
**PHASE 3B (SAM Runtime & Deployment):** COMPLETE — IMPLEMENTED, TESTED OFFLINE, REAL-PROCESS TESTED. See `docs/architecture/RUNTIME.md` and `docs/deployment/LOCAL_RUNTIME.md`.
**PHASE 3B FOLLOW-UP (config centralization + two known-bug fixes + one newly-discovered fix):** COMPLETE — IMPLEMENTED, TESTED OFFLINE, REAL-PROCESS TESTED. Detailed below.

No further software-only gap is currently identified against the PDR
reference and phase docs. Remaining work is hardware/event-dependent —
see **Next Action** at the bottom of this file.

---

## Phase 1 — Phone Surface & Execution Gateway (COMPLETE)

`iqoo/task_store.py`, `iqoo/events.py`, `iqoo/gateway.py`,
`iqoo/schemas.py`, `iqoo/server.py`, `client/`, additive `on_event`
callback in `agent/react_loop.py`. **IMPLEMENTED, TESTED OFFLINE.**

## Phase 2 — Multimodal Phone-to-PC Intelligence (COMPLETE)

`iqoo/errors.py`, `iqoo/media_validation.py`, `iqoo/vision_adapter.py`,
`iqoo/audio_adapter.py`, `client/audio.js`, camera/audio capture in the
client. **IMPLEMENTED, TESTED OFFLINE.** Vision/audio interpretation
quality against real models/hardware: **UNVERIFIED.**

## Phase 3A — Reliability & Recovery (THIS SESSION)

**Status: IMPLEMENTED, TESTED OFFLINE (44/44 new checks).**

### A. SSE reliability — IMPLEMENTED, TESTED OFFLINE

`iqoo/events.py` rewritten: full ordered, sequence-numbered history per
task (replacing Phase 1/2's single-consumer `queue.Queue`, which is the
actual mechanism that was losing events/terminal-status on reconnect —
not a hypothetical gap, a real one). `iqoo/server.py`'s SSE endpoint now
reads the standard `Last-Event-ID` header (sent automatically by
browsers' `EventSource` on reconnect) and replays everything after that
point, including an already-reached terminal status, before continuing
live. History is only ever cleared by an explicit demo reset, never by
a stream disconnecting.

**Real bug found and fixed:** a reconnect already caught up to an
already-terminal task (empty backlog, and no future event will ever
come, since `EventBus.publish` now refuses to append after a terminal
event) looped on heartbeats forever instead of closing — found because
the offline test for this genuinely hung during development. Fixed by
re-checking the task's DB status on every empty `wait_for_new` before
looping again.

### B. Task lifecycle robustness — IMPLEMENTED, TESTED OFFLINE

State set unchanged (already coherent from Phase 2). Added: once a task
reaches a terminal status, `TaskStore.update_status` and
`EventBus.publish` refuse any further write for that task_id — this is
what makes the timeout/orphan-recovery trade-offs below safe (an
orphaned thread finishing late can never silently flip a reported
outcome).

### C. Timeout handling — IMPLEMENTED, TESTED OFFLINE, with a documented trade-off

`TaskGateway._run_task_with_timeout` (default 600s, configurable via a
constructor param) runs `_process_task` on a nested thread and reports
`failed` (with a specific timeout message, plus an SSE event) the
moment the ceiling is hit — the phone is never left waiting
indefinitely. **Honest limitation, not hidden:** nothing in Python can
forcibly kill a thread blocked inside a synchronous Hands call or an
unbounded network request — the FIFO worker thread still waits for the
orphaned thread to actually finish before touching Hands again, to
preserve the single-flight invariant. See `ARCHITECTURE.md`.

### D. Retry safety — IMPLEMENTED, TESTED OFFLINE

`retry_task` now raises `TaskAlreadyActiveError` (→ HTTP 409) when
asked to retry a task that hasn't reached a terminal status —
previously this was silently allowed, a real latent bug (two competing
attempts at the same instruction). Added a `retried_from` column for
debugging history. Fresh-cancel-state-per-retry was already correct in
Phase 1/2; now explicitly tested rather than assumed.

### E. Worker recovery — IMPLEMENTED, TESTED OFFLINE

**Real bug found and fixed:** moving `_process_task` onto a nested
thread for the timeout watchdog (item C) initially dropped the
exception handling that used to wrap it directly — an exception raised
outside `_process_task`'s own inner try/except would propagate out of
the nested thread silently (Python swallows uncaught thread exceptions
rather than crashing the process), leaving that task stuck non-terminal
forever. This would have broken "task A fails, task B still executes"
in exactly the scenario it's meant to guarantee. Caught by
`test_worker_recovery_task_a_fails_task_b_still_executes` before it
shipped, fixed with an explicit catch-all in the nested thread's target
function.

### F. Demo reset — IMPLEMENTED, TESTED OFFLINE

`TaskGateway.reset_demo_state()` / `POST /api/iqoo/demo/reset` deletes
all task rows and event history. Refuses (`DemoResetBusyError` → 409)
while a task is active or queued. Verified via AST inspection (not just
behavioral testing) that neither `TaskStore.reset_demo_state` nor
`EventBus.reset_all` reference `memory`/`founder_mode` anywhere in
their actual code — SAM's real long-term memory cannot be touched.

### G. Health diagnostics — IMPLEMENTED, TESTED OFFLINE

`health()` now reports `worker_alive`, `vision_model_available`
(`None`/`True`/`False` — three-valued, since "Ollama unreachable" and
"reachable but model missing" are different problems), `whisper_available`
(cheap importability check, no model load), `uptime_seconds`, and an
overall `status` of `"degraded"` if the worker died or the brain is
unreachable. No task content, attachments, or other user data included.

### H. Tests — IMPLEMENTED

`tests/test_iqoo_phase3a_offline.py` — 44 checks. `tests/test_iqoo_phase1_offline.py`'s
`test_event_bus` was extended (new `EventBus` API) and a new
`test_event_bus_reconnect_and_terminal_guard` added; no existing check
was weakened or deleted, only the two `subscribe_queue`-based call sites
were migrated to the new backlog API (`get_since`) since that method no
longer exists.

### Two real bugs found during this checkpoint (both documented above and in `ARCHITECTURE.md`, not fixed silently)

1. SSE reconnect-already-caught-up infinite heartbeat loop (item A).
2. Worker-recovery exception-swallowing gap introduced by the timeout
   refactor itself (item E).

Finding and fixing both live in this session is exactly why the
protocol requires implement→test→document→commit per checkpoint rather
than batching all of Phase 3 — the tests caught real defects in code
written minutes earlier.

### Test results

- `tests/test_iqoo_phase3a_offline.py`: **44/44 passing.**
- `tests/test_iqoo_phase1_offline.py`: **56/56 passing** (49 prior + 2
  event-bus tests updated/added for the new API + 5 unaffected).
- `tests/test_iqoo_phase2_offline.py`: **51/51 passing, unaffected.**
- All 11 pre-existing `tests/*_offline.py` SAM suites: **unaffected.**
- `git diff --check`: clean.

### Hardware validation status: UNVERIFIED (unchanged from Phase 2)

No real Ollama, faster-whisper, phone, camera, microphone, or Office Kit
hardware was used anywhere in this checkpoint. Server-restart recovery
(item A/orphan recovery) was validated by constructing a fresh
`TaskStore` instance against the same on-disk SQLite file within the
same test process — this proves the recovery *logic* is correct, but is
**not** the same as an actual process kill + restart, which has not
been performed.

### Known risks / remaining gaps

- Timeout's "worker waits for the orphaned thread" trade-off means a
  truly hung, uninterruptible Hands call still occupies the worker for
  longer than `task_timeout_seconds`, even though the phone is told
  "failed" promptly. A forced kill would require either a
  multiprocessing-based execution model or making Hands cooperatively
  cancellable — both are real rewrites, explicitly out of scope per the
  "do not rewrite Hands" rule.
- Demo reset has no dedicated on-disk demo *workspace* yet (e.g. a
  `~/.sam_data/iqoo_demo/` for generated backend code/tests) — it only
  resets the task gateway's own bookkeeping (task rows + event
  history). A file-system demo workspace is Phase 3G (per the newer,
  expanded Phase 3 structure) / originally-numbered Phase 3C scope, not
  this checkpoint's.
- The AudioAdapter→`ears/stt.py` private-attribute coupling from Phase 2
  is unchanged and still flagged as a recommended fast-follow.
- No literal SSE test against a real browser's `EventSource` — the
  reconnect logic is tested by calling the server module's `event_stream`
  generator function directly (by design, for testability without a
  live HTTP connection), not through an actual HTTP round-trip.

**Next Action:** Wait for "Continue to Phase 3B." Per the newer,
expanded Phase 3 structure (checkpoints 3A–3H), 3B is "SAM Runtime &
Deployment" (a `sam start/stop/status/doctor`-style runtime management
layer) — a larger scope change from the original 4-checkpoint Phase 3
plan, not yet started.

**Last Commit:** Not yet committed — pending this checkpoint's
completion report, per the "implement → test → document → commit →
push → report → STOP" protocol.

---

## Phase 3A.5 — Migration to canonical SAM architecture (COMPLETE)

**Status: IMPLEMENTED, TESTED OFFLINE (106/106 new architecture-boundary
checks). Full detail in `PHASE_3A5_MIGRATION.md`; summarized here.**

Restructured the iQOO-specific code into SAM's long-term canonical
package layout, with zero behavior change:

- `iqoo/{gateway,task_store,events,schemas,server,vision_adapter,
  audio_adapter,media_validation,errors}.py` → `interfaces/api/*` and
  `multimodal/{audio,vision}/*`.
- `ecosystem/{telegram_bridge,pair_new_device}.py` → `interfaces/telegram/*`.
- `ecosystem/device_registry.py` → `connect/core/device_registry.py`.
- `client/` → `interfaces/web/`.

`iqoo/` and `ecosystem/` are kept as thin forwarding shims (e.g.
`iqoo/server.py` is just `from interfaces.api.server import app, main`)
— nothing that imports the old paths breaks. `connect/bridges/vivo_iqoo/`
exists as a documentation stub only; no vendor SDK, pairing mechanism, or
transport layer was fabricated for it.

`tests/test_architecture_boundaries_offline.py` (106 checks) verifies the
migration didn't just move files but preserved identity and behavior:
shim objects are the *same object* as their canonical counterparts (not
re-implementations), HTTP routes are unchanged, and the on-disk
`~/.sam_data/iqoo/tasks.db` path did not move (no data migration
needed).

**Not committed** — sits in the working tree, per the
implement→test→document→(await approval)→commit protocol.

## Phase 3B — SAM Runtime & Deployment (COMPLETE)

**Status: IMPLEMENTED, TESTED OFFLINE (85/85 new checks across three
suites), REAL-PROCESS TESTED. Full detail in
`docs/architecture/RUNTIME.md` and `docs/deployment/LOCAL_RUNTIME.md`;
summarized here.**

Added `runtime/` — a small process-lifecycle layer that knows how to
start, stop, restart, and health-check SAM's three independent entry
points (`main.py`, `interfaces/api/server.py`,
`interfaces/telegram/telegram_bridge.py`) without changing what any of
them do:

- `runtime/lifecycle/specs.py` — `ProcessSpec` + `default_specs()`.
- `runtime/lifecycle/manager.py` — `SAMRuntime` (start/stop/restart,
  PID-reuse-safe signaling via `cmdline_fragment`).
- `runtime/lifecycle/state.py` — one JSON state file per process under
  `~/.sam_data/runtime/`.
- `runtime/health/status.py` — six-state `RuntimeStatus`
  (`RUNNING`/`DEGRADED`/`STOPPED`/`STARTING`/`STOPPING`/`FAILED`).
- `sam_cli.py` — `start`/`stop`/`restart`/`status`/`doctor` wired to
  `SAMRuntime`.

**Honest readiness-signal distinction, not glossed over:** only `api` has
a real HTTP health endpoint. `voice` and `telegram` expose no queryable
readiness signal at all today, so their "ready" check is genuinely just
"still alive after a short grace period" — not equivalent to `api`'s
check, and documented as such rather than presented with the same
confidence.

**Real bug found and fixed:** `cmd_skills` was referenced in
`sam_cli.py`'s command dispatch table but never defined — a `NameError`
on import that crashed *every* CLI command, since Python evaluates the
whole dispatch dict at module load time. Pre-existing since the CLI's
initial commit; found and fixed as part of this checkpoint's audit, not
a Phase 3B regression.

**REAL-PROCESS TESTED** (not REAL-DEVICE TESTED — see the status-label
note at the top of this file): `interfaces.api.server` started as an
actual local OS process via `sam start api`, polled live via `sam
status`/`sam doctor`, restarted (confirmed via a *different* PID), and
stopped gracefully. `voice` and `telegram` have not been REAL-PROCESS
TESTED — see the hardware validation checklist under Next Action.

### Phase 3B follow-up — config centralization + two known-bug fixes (COMPLETE, this session)

Three small, separately-scoped fixes, each IMPLEMENTED, TESTED OFFLINE,
and REAL-PROCESS TESTED where applicable:

1. **Config centralization.** `RUNTIME.md` §6 flagged this as an open
   gap: `interfaces/api/server.py`'s host/port,
   `runtime/lifecycle/specs.py`'s `health_url`, and `sam_cli.py doctor`'s
   port-free check each held an independent literal `0.0.0.0:8420` —
   three copies that happened to agree, not centralization. Added
   `Settings.api_host`/`api_port` (default unchanged); all three now
   read the same `Settings()` instance. Proven end-to-end with a real
   process bound to a *non-default* overridden port (54999), not just an
   offline mock. `tests/test_runtime_config_offline.py` — 16/16.
2. **`cmd_logs` path mismatch, fixed.** `main.py` wrote its log file to a
   bare relative path `"logs/sam.log"` — resolved against whatever the
   process's current working directory happened to be, and a *different*
   file than `sam_cli.py`'s `cmd_logs`, which reads
   `SAM_DATA_DIR/logs/sam.log`. This only ever appeared to work because
   the repo ships a committed `logs/.gitkeep` at its own root. `main.py`
   now writes to the same `SAM_DATA_DIR`-based path `cmd_logs` already
   read from — the same fix pattern as (1): make both sides read one
   shared expression instead of holding independent copies.
3. **`pgrep -f main.py` false-positive risk, narrowed.** `sam status`'s
   legacy "SAM process" line ran a system-wide `pgrep -f main.py`, which
   any unrelated process with "main.py" anywhere in its command line
   would match. Now prefers the Phase-3B runtime-tracked state (one
   specific recorded PID, liveness-checked, cmdline-fragment-checked)
   when it exists; falls back to the original pgrep only when SAM was
   started outside `sam start` (e.g. `python main.py` run directly) —
   and that fallback is now honestly labeled best-effort rather than
   shown with the same confidence as a verified match. This does not
   eliminate the false-positive risk for that fallback path entirely (a
   truly collision-proof check would need `/proc`-based cwd
   verification, Linux-only, judged out of proportion to the reported
   bug); it narrows the risk substantially for the common `sam start`
   path.

`tests/test_cli_diagnostics_offline.py` — 14/14, covering both (2) and
(3) functionally: a real throwaway log file is written and read back
end-to-end; a real (but non-SAM) dummy process stands in for PID-liveness
and PID-reuse scenarios.

4. **Process leak in `test_runtime_cli_offline.py`, found and fixed —
   not one of the two originally-known bugs, discovered during this
   session's own investigation.** While tracking down why a real
   `interfaces.api.server` process kept turning up unexpectedly during
   this session's testing, traced it to
   `test_every_command_survives_dispatch()`: it runs `start api`, `stop
   api`, `restart api` as three genuinely separate real subprocesses
   (each `sam_cli.py` invocation is its own OS process — a `mock.patch`
   in the test's own process can't reach into a different one), but each
   got its own fresh, disconnected `HOME`. `stop api` was therefore
   checking a completely different, empty `~/.sam_data` than the one
   `start api` had just written its state to — it could never actually
   find or stop what `start` spawned. Confirmed empirically via
   bisection (running each suite alone, checking for a leftover process
   after each), not assumed. Fixed by having `start`/`stop`/`restart api`
   specifically share one `HOME` with each other, plus an unconditional
   safety-net stop after the loop — using the real, already-proven
   `SAMRuntime.stop()` directly (a bare `os.kill(SIGTERM)` was tried
   first and found insufficient: this process doesn't exit within 1s of
   a bare SIGTERM, and `SAMRuntime.stop()`'s poll-and-escalate-to-SIGKILL
   behavior is exactly why it's the right tool to reuse here rather than
   reinventing a weaker version). Verified by running the suite 5
   consecutive times and confirming zero leaked processes after every
   run, not just once. No new checks added (still 31/31,
   `test_runtime_cli_offline.py`) — this fixed how the suite manages its
   own subprocess resources, not what it verifies.

**Full regression after this follow-up: 513/513, 20 suites, 0 failures**
(up from 499/499/19 before this follow-up, and 483/483/18 before that —
each increase is exactly the new suite's own check count. Item 4 above
doesn't change this number: it fixed a resource leak, not a check
count.)

**Not committed** — same as 3A.5/3B, sits in the working tree pending
explicit approval.

---

**Next Action:** No further software-only gap is currently justified
against the PDR reference + phase docs. Remaining work is
hardware/event-dependent: `voice`/`telegram` real-process start, real
vision/audio model quality, real phone round-trip, live Telegram bot,
real Office Kit, Windows/macOS `sam doctor` paths, and the PDR's own
≥9/10-repeated-runs bar — none of which can be honestly produced from a
sandbox. 3C–3H numbering is explicitly not treated as required scope
(the authoritative PDR defines three official phases, not eight).

**Last Commit:** Still not committed — 3A.5, 3B, and this follow-up all
sit in the working tree together, pending explicit approval, per the
"implement → test → document → (commit if authorized) → package →
report → stop" protocol.
