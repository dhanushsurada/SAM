# iQOO Branch — Progress

**Current Phase:** Phase 1 — Phone Surface & Execution Gateway

**Phase Status:** Complete, awaiting explicit "Continue to Phase 2"

**Completed:**
- `hackathon/iqoo-2026` branch created (repo had no git history in the
  provided zip — initialized fresh, committed baseline as `master` first)
- `agent/react_loop.py` — additive `on_event` callback param on
  `run_task`/`run_planned_task` (default `None`, zero behavior change for
  existing callers). Only non-`iqoo/`/`client/`/`tests/`/`docs/` file
  touched in this whole branch.
- `iqoo/task_store.py` — SQLite task bookkeeping at `~/.sam_data/iqoo/tasks.db`
- `iqoo/events.py` — thread-safe event bus, sync worker → async SSE bridge
- `iqoo/schemas.py` — Pydantic task/event contract
- `iqoo/gateway.py` — `TaskGateway`: single worker thread + FIFO queue,
  real cancellation via `threading.Event`, invokes the same
  `brain.process` / `react_loop.run_planned_task` entry points `main.py`
  uses — no duplicated orchestration
- `iqoo/server.py` — FastAPI app, all 6 endpoints, static-mounts `client/`
- `client/` — phone web surface: home/composer, live phase checklist,
  camera + voice entry points, cancel/retry, error banner
- `tests/test_iqoo_phase1_offline.py` — 37/37 checks passing
- All 12 pre-existing `tests/*_offline.py` suites re-run and passing
  unchanged (zero regressions)
- `requirements.txt` updated (fastapi, uvicorn, httpx)
- `docs/iqoo/` — IQOO_PDR.md, ARCHITECTURE.md, PROTOCOL.md,
  OFFICE_KIT.md, DEMO.md, TEST_PLAN.md, TROUBLESHOOTING.md, this file

**In Progress:** Nothing — Phase 1 vertical slice is functionally complete.

**Blocked:**
- Manual phone→SAM→execution→result test not yet performed anywhere
  (no real Mac/Ollama/phone available in this build environment). Must
  be run for real before trusting this for the competition. This is not
  a code gap, it's a "hasn't been run on real hardware yet" gap.
- Office Kit's actual behavior is unverified (see `OFFICE_KIT.md`'s three
  stated assumptions) — nothing to fix, just needs verification against
  the real event-provided kit before September.

**Tests:** 37/37 new + 12/12 existing suites green. See `TEST_PLAN.md`
for exact coverage and the honestly-listed gaps (reconnect, timeout,
literal mid-stream disconnect).

**Known Bugs:** None found. **Known Gaps (not bugs, scoped-out-on-purpose):**
- No task-level timeout (Phase 3)
- No SSE event backlog/replay on reconnect (Phase 3)
- No demo reset infrastructure (Phase 3)
- Image/voice attachments accepted by the schema but rejected honestly
  by the worker (Phase 2)
- Voice entry point is browser dictation, not SAM's own Whisper pipeline
  (Phase 2)

**Next Action:** Wait for "Continue to Phase 2." When it comes, Phase 2
work is: camera image actually submitted as an attachment, a vision
adapter turning it into structured context (reuse `hands/vision/`, do
not rewrite it), server-side STT for real phone-mic voice, and the
whiteboard-schema → tested FastAPI backend demo workflow end to end.

**Last Commit:** See `git log` on `hackathon/iqoo-2026` —
`feat(iqoo): add phone task gateway` (this phase's squashed/organized
commits, per the PDR's commit discipline in section 15).
