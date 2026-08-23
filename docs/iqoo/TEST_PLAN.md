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

## Full regression (re-verified for Phase 2)

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

## Known gaps (honest, not hidden)

### Carried over from Phase 1
1. **Disconnected client** — still only partially covered (see Phase 1
   notes below); unchanged in Phase 2.
2. **Reconnect** — still Phase 3 scope.
3. **Timeout handling** — still Phase 3 scope; note that a hung
   perception call (not just a hung Brain call) is now also unbounded
   for the same reason.
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
3. **Timeout handling** — no task-level timeout exists yet in
   `iqoo/gateway.py`; a stuck Brain or perception call blocks that task
   indefinitely (though the worker thread and other queued tasks are
   unaffected — confirmed for perception specifically by
   `test_gateway_perception_timeout_like_failure`). Phase 3 scope per
   the PDR.

These gaps are intentionally listed in `PROGRESS.md` under "Known Bugs"
and "Next Action" rather than silently left out of this document.
