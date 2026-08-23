# SAM iQOO Phone Client (Phase 1)

Minimal phone-facing web surface for the iQOO Hackathon 2026 branch.
Vanilla HTML/CSS/JS — no framework, no build step, no npm install.

## Why no framework

PDR 8.2 asks for "the least disruptive technology compatible with the
current repository." SAM's stack is Python; adding a JS build toolchain
just for this branch would be scope creep for a 30-hour competition
window. This is a single static folder served by `iqoo/server.py`.

## Running it

It's served automatically when the gateway is running:

```bash
python -m iqoo.server
```

Then open `http://<laptop-ip>:8420/` on the phone (same WiFi, or through
Office Kit's mirrored browser during Red Light).

## Files

| File | Role |
|---|---|
| `index.html` | Markup — home/composer view + execution progress view |
| `styles.css` | Mobile-first dark theme, no dependencies |
| `state.js` | Single plain-object app state |
| `api.js` | fetch() wrapper for `/api/iqoo/*` |
| `events.js` | SSE subscription (`EventSource`) for live execution progress |
| `camera.js` | Camera capture — encodes the photo to base64, shows a real preview, attaches it to the task (Phase 2: actually submitted now) |
| `audio.js` | Voice note recording via `MediaRecorder` — records real audio, attaches it to the task for SAM's server-side Whisper transcription (Phase 2) |
| `voice.js` | Separate dictation entry point — browser `SpeechRecognition` typing directly into the text box (push-to-talk, client-side only, not sent to SAM as audio) |
| `app.js` | Wires everything together: composes the multimodal request (text/image/voice/image+voice), submit, cancel, retry, render loop |

## Phase 2 scope (what actually works)

- Everything from Phase 1, unchanged (text tasks, cancel, retry, SSE)
- Camera capture → real preview → actually submitted as a task attachment
- Voice note recording → actually submitted as a task attachment →
  transcribed server-side by SAM's Whisper pipeline
- Combined image+voice submission (the primary whiteboard-to-backend
  demo shape)
- A `perceiving` phase in the progress checklist while SAM's vision/audio
  adapters interpret the attachment(s)
- Client-side MIME/size pre-checks (reject obviously-bad files before
  even uploading) — the server re-validates independently regardless

## Not yet built (Phase 3)

- Demo reset / seeded environment
- SSE reconnect with event backlog/replay
- Task-level timeout surfaced to the UI

## Untested (all phases, honestly)

Nothing in `client/` has been run against a real mobile browser, a real
camera, or a real microphone in this build environment. The camera/audio
capture code was written against the standard File API / MediaRecorder
API specs, but browser quirks (especially iOS Safari's historically
inconsistent `MediaRecorder` support) are common and none have been
found yet, because nothing has touched a real device.
