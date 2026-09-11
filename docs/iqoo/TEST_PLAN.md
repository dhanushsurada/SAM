# iQOO Branch — Test Plan

## Phase 1 automated coverage

`tests/test_iqoo_phase1_offline.py` — 37 checks, all offline (no Ollama,
no network, no real phone). Run with:

```bash
HOME=/tmp/sam_iqoo_test python3 tests/test_iqoo_phase1_offline.py
```

Covers, against the PDR's minimum test list (section 13):

| Requirement | Covered by |
|---|---|
| Valid request | `test_gateway_no_action_task`, `test_gateway_action_task`, `test_api_endpoints` |
| Invalid request | `test_api_endpoints` (empty/missing `instruction` → 422) |
| Duplicate request doesn't corrupt state | `test_gateway_retry` (two independent task_ids never mix state) |
| Task cancellation | `test_gateway_cancel_before_start` (queued task never executes after cancel) |
| Execution failure | `test_gateway_execution_failure` (Brain exception → `failed`, error captured) |
| Missing/unsupported input (image/voice not yet processable) | `test_gateway_unsupported_input_type` |
| Reconnect | **Not covered — see gaps below** |
| Timeout | **Not covered — see gaps below** |
| Repeated execution | `test_gateway_retry` |
| Disconnected client | **Partially covered — see gaps below** |

## Phase 2 automated coverage

`tests/test_iqoo_phase2_offline.py` — 51 checks, all offline/mocked (no
real Ollama, no real faster-whisper, no real phone/camera/microphone).
Run with:

```bash
HOME=/tmp/sam_iqoo_phase2_test python3 tests/test_iqoo_phase2_offline.py
```

Covers, against Phase 2's required test list:

| Requirement | Covered by |
|---|---|
| Text-only Phase 1 compatibility | `test_backward_compat_text_only_schema` |
| Valid image input | `test_media_validation_helpers`, `test_gateway_image_text_task_builds_structured_context` |
| Invalid image MIME rejection | `test_media_validation_helpers` |
| Oversized image rejection | `test_media_validation_helpers` |
| Image/task association | `test_gateway_retry_preserves_attachments` |
| Multimodal schema validation | `test_task_create_request_multimodal_validation` |
| Audio input validation | `test_media_validation_helpers` |
| Malformed audio rejection | `test_media_validation_helpers`, `test_audio_adapter_success_and_failure` |
| Mocked STT adapter | `test_audio_adapter_success_and_failure` |
| Mocked vision adapter | `test_vision_adapter_success_and_failure` |
| image+text → structured perception context | `test_gateway_image_text_task_builds_structured_context` |
| Perception failure | `test_gateway_perception_failure_reports_cleanly` |
| Perception timeout/failure handling | `test_gateway_perception_timeout_like_failure` |
| Event emission | `test_task_store_perceiving_status`, all gateway integration tests check status transitions |
| Cancellation during perception | `test_gateway_cancellation_during_perception` (also caught a real bug — see `PROGRESS.md`) |
| Task retry | `test_gateway_retry_preserves_attachments` |
| Concurrency serialization remains intact | `test_concurrency_serialization_unaffected_by_perception` |
| Existing ReactLoop remains the execution engine | `test_gateway_image_text_task_builds_structured_context` asserts the Brain receives plain text, never an image/audio byte |
| No duplicated planner/execution logic | Architectural — `_perceive()` only produces text, never calls Planner/ReAct itself (see `ARCHITECTURE.md`) |
| Phase 1 tests still pass | Full `tests/test_iqoo_phase1_offline.py` re-run, 44/44 (one test updated — see below) |

### Note on the one changed Phase 1 test

`test_gateway_unsupported_input_type` (Phase 1) asserted that ANY
non-text task fails with a hardcoded "Phase 2" message — that assertion
describes exactly the limitation Phase 2 removes by design. It was
renamed to `test_gateway_perception_failure_handled_gracefully` and now
asserts the more general, still-true invariant: a perception failure
(mocked) still fails the task cleanly without reaching the Brain. Every
other Phase 1 test is byte-for-byte unchanged.

## Phase 3A automated coverage

**[IMPLEMENTED, TESTED OFFLINE]** `tests/test_iqoo_phase3a_offline.py` —
44 checks, fully offline (no real Ollama, faster-whisper, phone, or
Office Kit). Server-restart recovery is simulated via a fresh
`TaskStore` instance against the same on-disk DB, not an actual process
kill/restart — see `PROGRESS.md` for what remains **[UNVERIFIED]**
pending real hardware. Run with:

```bash
HOME=/tmp/sam_iqoo_phase3a_test python3 tests/test_iqoo_phase3a_offline.py
```

| Requirement | Covered by |
|---|---|
| SSE reconnect (cold, partial, already-caught-up) | `test_sse_event_stream_reconnect_no_duplicates` |
| Duplicate event prevention | `test_event_bus_reconnect_and_terminal_guard` (Phase 1 suite), `test_sse_event_stream_reconnect_no_duplicates` |
| Terminal state recovery after reconnect | `test_event_bus_reconnect_and_terminal_guard`, `test_sse_event_stream_reconnect_no_duplicates` |
| Timeout | `test_task_timeout_reports_promptly_and_does_not_get_clobbered` |
| Worker recovery (task A fails, task B still runs) | `test_worker_recovery_task_a_fails_task_b_still_executes` |
| Queue continuation after a failure/timeout | `test_queue_continues_after_timeout` |
| Retry safety (non-terminal rejection, history, fresh cancel state) | `test_retry_rejects_non_terminal_task`, `test_retry_records_history_and_fresh_cancel_state` |
| Server-restart / orphan recovery | `test_orphaned_task_recovery_on_restart`, `test_gateway_recovers_orphans_at_startup` |
| Demo reset (success + busy guard + memory isolation) | `test_demo_reset_clears_state_and_respects_busy_guard`, `test_demo_reset_never_touches_memory_or_founder_mode` |
| Health diagnostics | `test_health_reports_expanded_diagnostics`, `test_health_reports_worker_dead_after_shutdown` |

Two real bugs were found and fixed while writing this suite (both
documented in `ARCHITECTURE.md`'s Phase 3A section, not just fixed
silently):
1. `event_stream`'s reconnect-already-caught-up case looped on
   heartbeats forever instead of closing — found because the offline
   test genuinely hung.
2. The timeout-watchdog refactor dropped exception handling for errors
   raised outside `_process_task`'s own inner try/except, which would
   have left a task stuck non-terminal forever — found by the
   worker-recovery test.

## Phase 3A.5 automated coverage

**[IMPLEMENTED, TESTED OFFLINE]** `tests/test_architecture_boundaries_offline.py`
— 106 checks. This phase is an internal restructure (iQOO code moved
into SAM's canonical package layout), not a new PDR requirement, so
there's no requirement table to map against — instead this suite proves
the migration preserved identity and behavior rather than just moving
files around:

| What's checked | Why it matters |
|---|---|
| Shim objects (`iqoo.server.app`, `iqoo.server.main`, etc.) are the *same object* as their canonical counterparts | Proves a forwarding shim, not a silent fork that could drift |
| HTTP routes unchanged after the move | Nothing that talks to the API over the network needs to change |
| `~/.sam_data/iqoo/tasks.db` path unchanged | No data migration was needed or performed |
| `connect/bridges/vivo_iqoo/` contains no `.py` files | No vendor SDK/pairing mechanism was fabricated for a phase that doesn't require one yet |

Full detail and the complete before/after file mapping: `PHASE_3A5_MIGRATION.md`.

## Phase 3B automated coverage

**[IMPLEMENTED, TESTED OFFLINE, REAL-PROCESS TESTED]** Three suites, 85
checks total. Full detail: `docs/architecture/RUNTIME.md`,
`docs/deployment/LOCAL_RUNTIME.md`.

| Requirement | Covered by |
|---|---|
| Start/stop/restart a process by `ProcessSpec` | `tests/test_runtime_lifecycle_offline.py` (32 checks, against throwaway dummy scripts — never real `main.py`/`interfaces.api.server`) |
| PID-reuse-safe signaling (`cmdline_fragment`) | `tests/test_runtime_lifecycle_offline.py` |
| Six-state `RuntimeStatus` (RUNNING/DEGRADED/STOPPED/STARTING/STOPPING/FAILED) | `tests/test_runtime_health_offline.py` (22 checks) |
| `sam start/stop/restart/status/doctor` dispatch, including the pre-existing `cmd_skills` crash | `tests/test_runtime_cli_offline.py` (31 checks, real CLI subprocess, fake runtime double) |
| Real local process start/stop/restart/health-poll | REAL-PROCESS TESTED manually (`interfaces.api.server`, both default and non-default ports) — not an automated offline check by nature; see `LOCAL_RUNTIME.md` |
| `voice`/`telegram` real-process start | **Not yet done — see Known gaps** |

### Phase 3B follow-up automated coverage (this session)

| Fix | Covered by |
|---|---|
| Config centralization (`Settings.api_host`/`api_port` as single source of truth for `server.py`, `specs.py`, `sam_cli.py doctor`) | `tests/test_runtime_config_offline.py` (16 checks) — proves it functionally via subprocess snapshots and a mocked `uvicorn.run`, plus REAL-PROCESS TESTED manually at a non-default overridden port (54999) |
| `cmd_logs` path mismatch fix | `tests/test_cli_diagnostics_offline.py` (14 checks) — writes a real log line via `main.py`'s actual logging setup, reads it back via the real `sam logs` CLI |
| `pgrep -f main.py` false-positive narrowing | `tests/test_cli_diagnostics_offline.py` — covers the verified-state path, the pgrep-fallback path, a live-but-mismatched-PID (simulated reuse) case, and a stale-dead-PID case |
| Process leak in `test_runtime_cli_offline.py` itself (self-discovered, not one of the two known bugs above) | Verified by running that suite 5 consecutive times and confirming zero leaked `interfaces.api.server` processes after every run — a leak wouldn't show up as a `[FAIL]` line (the suite's own assertions only check for uncaught Python errors), so this needed a process-table check, not just a green suite |

## Full regression (as of Phase 3A — historical, superseded below)

All 12 pre-existing `tests/*_offline.py` suites were re-run against this
branch and pass unchanged — this branch introduced zero regressions to
core SAM:

```
test_browser_thread_affinity_offline.py         PASS
test_concurrency_and_vision_fixes_offline.py     PASS
test_feature_tier_offline.py                     PASS
test_founder_mode_offline.py                     PASS
test_latency_fixes_offline.py                    PASS
test_licensing_offline.py                        PASS
test_persistent_memory_offline.py                PASS
test_phase15_offline.py                          PASS
test_phase1_offline.py                           PASS
test_phase2_telegram_offline.py                  PASS
test_task_request_and_stagnation_offline.py      PASS
```

(`test_founder_mode_live.py` is a live-only test by name and was not run,
consistent with how it's presumably excluded from other offline CI runs
in this repo.)

## Full regression (current — as of Phase 3B follow-up)

All 20 `tests/*_offline.py` suites, freshly run together, this session:

```
test_iqoo_phase1_offline.py                      56/56
test_iqoo_phase2_offline.py                      51/51
test_iqoo_phase3a_offline.py                     44/44
test_architecture_boundaries_offline.py         106/106
test_phase2_telegram_offline.py                  20/20
test_runtime_lifecycle_offline.py                32/32
test_runtime_health_offline.py                   22/22
test_runtime_cli_offline.py                      31/31
test_runtime_config_offline.py                   16/16
test_cli_diagnostics_offline.py                  14/14
test_phase1_offline.py                           14/14
test_phase15_offline.py                          22/22
test_founder_mode_offline.py                     10/10
test_persistent_memory_offline.py                 3/3
test_licensing_offline.py                        14/14
test_feature_tier_offline.py                      9/9
test_latency_fixes_offline.py                    16/16
test_browser_thread_affinity_offline.py          10/10
test_concurrency_and_vision_fixes_offline.py      7/7
test_task_request_and_stagnation_offline.py      16/16
------------------------------------------------------
TOTAL                                           513/513, 0 failures
```

(`test_founder_mode_live.py` — still live-only, still not run, same
reason as above.) Growth is accounted for exactly: 483/483 (18 suites)
at the Phase 3B baseline → 499/499 (19 suites) after
`test_runtime_config_offline.py` → 513/513 (20 suites) after
`test_cli_diagnostics_offline.py`. No suite lost checks; no number
changed without a suite added to explain it.

## Known gaps (honest, not hidden)

### Carried over from Phase 1
1. **Disconnected client** — still only partially covered (see Phase 1
   notes below); unchanged through Phase 2 and 3A.
2. ~~**Reconnect** — still Phase 3 scope.~~ **RESOLVED in Phase 3A** —
   `test_sse_event_stream_reconnect_no_duplicates` and
   `test_event_bus_reconnect_and_terminal_guard` (see the Phase 3A
   section above). Left here, struck through rather than deleted, so
   this document doesn't quietly erase that it was ever an open gap.
3. ~~**Timeout handling** — still Phase 3 scope.~~ **RESOLVED in Phase
   3A** — `test_task_timeout_reports_promptly_and_does_not_get_clobbered`
   (see the Phase 3A section above). Same note: struck through, not
   deleted.
4. **Manual phone→SAM→execution→result test** — still not performed on
   real hardware.

### New in Phase 2
5. **No real vision/audio model was ever called.** All 51 Phase 2 checks
   use mocked HTTP responses / mocked STT model objects. Whether
   moondream/llava actually produces a usable schema description from a
   real handwritten whiteboard photo, and whether faster-whisper
   actually transcribes a real phone recording well, is completely
   unverified. This is the single largest untested assumption in the
   whole branch — see `DEMO.md`.
6. **`AudioAdapter`'s coupling to `ears/stt.py` internals** (`_load_model()`,
   `_model`) is untested against a real loaded Whisper model — only
   against a hand-built fake model object with the same interface shape.
   If `_load_model()`'s actual behavior differs subtly from what the fake
   assumes, this would only surface on real hardware.
7. **No literal-connectivity image/audio round-trip test** — attachment
   base64 payloads in the Phase 2 suite are synthetic byte strings that
   pass validation but are not real decodable JPEG/WAV/webm data. A
   nonsensical-but-valid-looking payload could theoretically pass all
   current tests while still being rejected by a real Ollama/Whisper
   call for a completely different reason (e.g. "not a valid image")
   that these tests can't catch.

### New in Phase 3B / follow-up
8. **`voice` and `telegram` have never been REAL-PROCESS TESTED.** Only
   `interfaces.api.server` has actually been started as a real local
   process (twice: default port, and an overridden non-default port).
   `main.py` and `interfaces/telegram/telegram_bridge.py`'s "alive after
   grace period" readiness check has only ever run against throwaway
   dummy scripts, never the real entry points.
9. **`sam doctor`'s Windows (`tasklist`/`taskkill`) and macOS
   (`sysctl`)-specific branches have never run on Windows or macOS** —
   only the Linux/POSIX branch has executed, in this sandbox.
10. **`sam doctor`/`sam status` behavior with Ollama *actually running*
    is untested.** Every offline and real-process check so far has only
    ever observed the "Ollama unreachable" path.
11. **Live Telegram bot round-trip is untested, and not just
    unattempted** — this sandbox has no network route to Telegram's API
    at all (policy-blocked), so this is a harder blocker than "hasn't
    been tried yet."

Original Phase 1 disconnected-client/reconnect/timeout details:
1. **Disconnected client** — `test_api_endpoints` doesn't literally drop
   an SSE connection mid-stream (`TestClient` doesn't make that easy to
   simulate). The server-side handling (`request.is_disconnected()`
   check, `finally: event_bus.cleanup()`) exists and was manually
   reasoned through, but isn't exercised by an automated test yet.
2. **Reconnect** — Phase 1/2 have no reconnect semantics beyond "poll
   `GET /tasks/{id}` again and re-subscribe to SSE" — there's no test
   proving a client can resume a dropped stream without losing in-flight
   events published before it reconnected (the event queue has no
   replay/backlog). This is explicitly deferred to Phase 3.
3. **Timeout handling** — ~~no task-level timeout exists yet in
   `iqoo/gateway.py`~~. **Resolved in Phase 3A.** `interfaces/api/gateway.py`
   now enforces `task_timeout_seconds` (`_run_task_with_timeout`) so a
   stuck Brain or perception call fails that task instead of blocking
   indefinitely (though the worker thread and other queued tasks were
   already unaffected — confirmed for perception specifically by
   `test_gateway_perception_timeout_like_failure`). See
   `test_task_timeout_reports_promptly_and_does_not_get_clobbered` and
   `test_queue_continues_after_timeout` in `test_iqoo_phase3a_offline.py`.

(Items 2 and 3 immediately above are preserved as they read at the time
Phase 1/2 shipped — i.e. genuinely open then. Both were resolved in
Phase 3A; see items 2/3 under "Carried over from Phase 1" above for the
resolution and the tests that prove it. Kept here rather than deleted so
this document's own history stays legible.)

These gaps are intentionally listed in `PROGRESS.md` under "Known Bugs"
and "Next Action" rather than silently left out of this document.
