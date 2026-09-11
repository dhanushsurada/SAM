# iQOO Branch — Perception (Phase 2)

Covers the vision input contract, audio input contract, and the
multimodal task schema. For the overall pipeline diagram see
`ARCHITECTURE.md`; for the wire-level JSON shapes see `PROTOCOL.md`
(being extended alongside this file).

## What perception is and isn't

Perception (`multimodal/vision/adapter.py`, `multimodal/audio/adapter.py`,
`interfaces/api/gateway.py::_perceive`) converts phone attachments into plain
text. That text is folded into the `instruction` string handed to
`Brain.process()` exactly the way a typed task always was. **The Brain,
Planner, and ReAct loop never see an image or an audio byte** — only
text, indistinguishable in shape from Phase 1. Perception makes no
planning or execution decisions itself.

## Vision input contract

- Attachment `kind: "image"`, `mime_type` one of `image/jpeg`,
  `image/png`, `image/webp`, `data`: base64-encoded bytes (no `data:`
  URL prefix), max 8MB decoded.
- `multimodal/vision/adapter.py::VisionAdapter.interpret(attachment, instruction)`
  calls Ollama's `/api/generate` with the image and a prompt asking for
  a literal, thorough description framed by the instruction — same
  request shape as `hands/vision/screen_reader.py::ScreenReader.read()`,
  same `settings.vision_model` selection (moondream/llava). It does not
  call `ScreenReader` itself, because every `ScreenReader` method is
  hard-wired to `screencapture` (the LOCAL machine's screen) — the wrong
  data source for a photo the phone already took.
- Returns a plain string description. Raises `PerceptionError` on HTTP
  failure, unreachable Ollama, or an empty/malformed response — never
  silently returns an empty or fabricated description.

## Audio input contract

- Attachment `kind: "audio"`, `mime_type` one of `audio/webm`,
  `audio/wav`, `audio/x-wav`, `audio/mp4`, `audio/ogg`, `audio/mpeg`,
  `data`: base64-encoded bytes, max 15MB decoded.
- `multimodal/audio/adapter.py::AudioAdapter.transcribe(attachment)` writes the
  decoded bytes to a temp file and reuses `ears/stt.py`'s existing
  faster-whisper model (same `settings.whisper_model`, same
  `.transcribe(path, language="en", beam_size=5, vad_filter=True)` call
  shape as `SpeechToText.listen()`) — fed a file instead of a live mic
  recording. Falls back to the same `speech_recognition`+Google path
  `ears/stt.py` already uses if faster-whisper isn't installed, with one
  honest limitation: that fallback only accepts WAV/AIFF/FLAC via
  `sr.AudioFile`, so a webm/ogg/mp4 phone recording fails cleanly with a
  clear error in the fallback case rather than being silently
  mistranscribed or crashing.

### Known coupling (flagged, not hidden)

`AudioAdapter` reaches into `SpeechToText._load_model()` and
`SpeechToText._model` — underscore-prefixed, not a public API — instead
of a clean `transcribe_file(path)` method on `SpeechToText` itself. This
was a deliberate choice: adding that method is a genuinely trivial,
three-line, additive change, but it touches `ears/stt.py`, a file
outside `iqoo/`/`client/`/`tests/`/`docs/iqoo/`, and the Phase 2
instructions require stopping to justify any such change before making
it. Rather than pause mid-implementation for a change this small, the
adapter avoids touching `ears/stt.py` entirely and documents the
trade-off here. **Recommended fast-follow:** add
`SpeechToText.transcribe_file(path) -> str` as a public method (reusing
the exact same call the adapter makes today) and switch
`AudioAdapter` to call it — see `PROGRESS.md`.

## Multimodal task schema (Phase 2 additions)

`input_type` (unchanged set from Phase 1): `text | voice | image |
image+text | image+voice`.

`Attachment` (extended in Phase 2 — `mime_type` is now required):

```json
{
  "kind": "image",
  "mime_type": "image/jpeg",
  "data": "<base64, no data: prefix>",
  "filename": "schema.jpg"
}
```

Validated in two layers:
1. `interfaces/api/schemas.py`'s Pydantic model — MIME allowlist, base64
   well-formedness, size limit (via `multimodal/media_validation.py`), and
   that the declared `input_type` actually has the attachment(s) it
   requires. Failures here are a clean `422` before a task is ever
   created.
2. `interfaces/api/gateway.py::_perceive`'s own guard — belt-and-suspenders check
   that the required attachment is actually present in the task record,
   in case something reaches the gateway without going through the
   Pydantic layer.

### Structured context composition

For `image+text`: `"{typed instruction}\n\n[Image context — SAM's
vision model analysis of the attached photo]\n{vision description}\n[End
image context]"`.

For `voice`: the transcript becomes the instruction directly (combined
with any typed text, if present).

For `image+voice`: transcript + typed text (if any) + the same
`[Image context]` block, with vision's own framing instruction preferring
the transcript over the typed field (see the code comment in
`interfaces/api/gateway.py::_perceive` — this was a real bug caught by
`tests/test_iqoo_phase2_offline.py` before being fixed).

## Backward compatibility

A `text`-only `TaskCreateRequest` — the entire Phase 1 contract — parses
and executes identically to Phase 1. Confirmed by
`tests/test_iqoo_phase2_offline.py::test_backward_compat_text_only_schema`
and by re-running the full `tests/test_iqoo_phase1_offline.py` suite
unchanged (44/44 passing) after this work landed.
