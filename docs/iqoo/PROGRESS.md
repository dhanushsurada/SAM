# iQOO Branch — Progress

Status labels used throughout, per the Phase 3 protocol:
**IMPLEMENTED** · **TESTED OFFLINE** · **REAL-DEVICE TESTED** ·
**HARDWARE VERIFIED** · **UNVERIFIED** · **DEFERRED**

**PHASE 1:** COMPLETE
**PHASE 2:** COMPLETE
**PHASE 3A (Reliability & Recovery):** COMPLETE — IMPLEMENTED, TESTED OFFLINE.
Awaiting explicit "Continue to Phase 3B."

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
