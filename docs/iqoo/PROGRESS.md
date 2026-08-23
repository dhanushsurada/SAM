# iQOO Branch — Progress

**PHASE 1:** COMPLETE

**PHASE 2:** IN PROGRESS — implementation and offline/mocked testing
complete; real hardware validation NOT performed (no Mac/Ollama/phone/
camera/microphone available in this build environment). Awaiting
explicit "Continue to Phase 3."

---

## Phase 1 — Phone Surface & Execution Gateway (COMPLETE)

Implemented: `iqoo/task_store.py`, `iqoo/events.py`, `iqoo/gateway.py`,
`iqoo/schemas.py`, `iqoo/server.py`, `client/`, `docs/iqoo/`,
`tests/test_iqoo_phase1_offline.py`, additive `on_event` callback in
`agent/react_loop.py`. 44/44 offline checks passing (37 original + 3
explicit concurrency-serialization checks + one renamed/re-scoped test
— see Phase 2 test plan note). All 12 pre-existing SAM test suites
unaffected.

## Phase 2 — Multimodal Phone-to-PC Intelligence (THIS SESSION)

### Implemented components

- `iqoo/errors.py` — `PerceptionError`, `PerceptionCancelled`
- `iqoo/media_validation.py` — MIME allowlist, base64 well-formedness,
  size limits (8MB image / 15MB audio) for attachments
- `iqoo/vision_adapter.py` — `VisionAdapter.interpret()`, reuses the
  Ollama vision-model call shape already established by
  `hands/vision/screen_reader.py::ScreenReader` (same model selection,
  same `/api/generate` request), fed a phone-uploaded image instead of a
  local screenshot
- `iqoo/audio_adapter.py` — `AudioAdapter.transcribe()`, reuses
  `ears/stt.py::SpeechToText`'s model loading and faster-whisper call
  shape, fed an uploaded file instead of a live mic recording (see
  "Known coupling" below)
- `iqoo/schemas.py` — `Attachment` now requires `mime_type` and
  validates via `media_validation`; `TaskCreateRequest` validates that
  the declared `input_type` actually has the attachment(s) it needs
- `iqoo/task_store.py` — added `perceiving` to `ALL_STATUSES`
- `iqoo/gateway.py` — `_perceive()` method; `_process_task` now runs
  perception before `understanding`/`brain.process()` for any non-text
  task, with cancellation checks before AND after each adapter call
- `client/` — camera capture/preview/remove, audio recording with
  indicator, multimodal task composer, perception progress phase, error
  handling and retry for upload/perception failures (code written this
  session; **not exercised against a real browser/device**)
- `tests/test_iqoo_phase2_offline.py` — 51 checks, fully offline/mocked
- `tests/test_iqoo_phase1_offline.py` — updated: `make_mocked_gateway()`
  now also mocks `VisionAdapter`/`AudioAdapter` (so nothing in the Phase
  1 suite can accidentally reach real Ollama/Whisper); one obsolete test
  renamed and re-scoped (see Test Results below)
- `docs/iqoo/PERCEPTION.md` — new: vision/audio contracts, multimodal
  schema, structured-context composition rules
- `docs/iqoo/PROTOCOL.md`, `DEMO.md`, `TROUBLESHOOTING.md`,
  `ARCHITECTURE.md`, `TEST_PLAN.md` — updated for Phase 2

### Two real bugs found and fixed by the Phase 2 tests

1. **Cancellation gap:** a cancellation requested while a (blocking,
   uninterruptible) vision/audio call was in flight was not being
   re-checked once that call returned — the task would proceed into
   `brain.process()` anyway. Fixed by adding a `cancel_event.is_set()`
   check immediately after `_perceive()` succeeds, matching the same
   pattern already used after `brain.process()` and after
   `run_planned_task()`. Caught by
   `test_gateway_cancellation_during_perception`.
2. **Wrong instruction priority for `image+voice`:** vision was being
   framed by the typed `instruction` field first, falling back to the
   voice transcript second — backwards for the primary demo workflow,
   where the typed field is usually just a required placeholder (e.g.
   `"(voice command)"`) and the transcript is the substantive request.
   Fixed to prefer the transcript. Caught by
   `test_gateway_image_voice_task_combines_both`.

### Known coupling (flagged, not hidden)

`AudioAdapter` reaches into `ears/stt.py::SpeechToText`'s
underscore-prefixed `_load_model()` and `_model` instead of a clean
public method, specifically to avoid touching a file outside
`iqoo/`/`client/`/`tests/`/`docs/iqoo/` without stopping to justify it
first (per the Phase 2 instructions). The correct long-term fix — a
three-line additive `transcribe_file(path)` public method on
`SpeechToText` — was deliberately NOT made this phase. See
`PERCEPTION.md` and "Next Action" below.

### Test results

- `tests/test_iqoo_phase2_offline.py`: **51/51 passing**, all
  offline/mocked (no real Ollama, no real faster-whisper, no real
  phone/camera/microphone).
- `tests/test_iqoo_phase1_offline.py`: **44/44 passing** after one
  necessary update — `test_gateway_unsupported_input_type` (which
  asserted Phase 1's now-removed "all non-text tasks fail" behavior) was
  renamed to `test_gateway_perception_failure_handled_gracefully` and
  re-scoped to assert the still-true invariant (a perception failure
  fails the task cleanly without reaching the Brain), using
  `make_mocked_gateway()`'s new `VisionAdapter`/`AudioAdapter` mocks.
  Every other Phase 1 test is unchanged.
- All 12 pre-existing `tests/*_offline.py` SAM suites: **unaffected**,
  re-run and passing in this environment.
- `git diff --check`: clean, no whitespace errors.

### Hardware validation status: NOT PERFORMED

No real Ollama vision-model call, no real faster-whisper transcription,
no real iQOO camera/microphone, no real Office Kit — none of these were
exercised anywhere in this session. Everything above is offline/mocked
logic verification only. This must happen for real before Phase 2 is
trusted for the competition.

### Remaining Phase 2 work / known risks

- Real hardware validation (blocking, see above).
- `AudioAdapter`'s coupling to `SpeechToText` internals is untested
  against a real loaded Whisper model (only a hand-built fake with the
  same shape) — see `PERCEPTION.md`.
- Phone client camera/audio code has not been run in an actual mobile
  browser; `MediaRecorder`/camera-capture browser API quirks are common
  and none have been discovered yet because nothing has touched a real
  device.
- No literal end-to-end round-trip test with real (not synthetic)
  JPEG/WAV/webm bytes — see `TEST_PLAN.md`'s Phase 2 known gaps.
- Task-level timeout still doesn't exist for perception any more than it
  did for Brain calls in Phase 1 (Phase 3 scope, unchanged).

### Termux environment note (not an iQOO issue)

The user's Termux environment (Python 3.13.13 + cryptography 50.0.0)
has a pre-existing, reproduces-without-iQOO native-extension issue in
`tests/test_feature_tier_offline.py` (`_rust.abi3.so` can't resolve
`PyBaseObject_Type`). Per instruction, licensing was NOT modified to
work around this — it's an environment/toolchain issue, not a
regression from this branch.

**Next Action:** Wait for "Continue to Phase 3." Recommended fast-follow
independent of Phase 3: add `SpeechToText.transcribe_file(path)` as a
public method on `ears/stt.py` and switch `AudioAdapter` to use it
instead of `_load_model()`/`_model` directly (see "Known coupling"
above) — flagged rather than done automatically, since it touches a file
outside this branch's primary working directories.

**Last Commit:** Not yet committed — this phase's changes are staged
locally pending the completion report and explicit go-ahead, per the
Phase 2 instructions ("Do NOT commit immediately. First produce a
completion report.").
