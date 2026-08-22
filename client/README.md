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
| `camera.js` | Camera entry point — captures a photo but does not yet submit it (Phase 2 wires real multimodal submission) |
| `voice.js` | Voice entry point — browser `SpeechRecognition` dictation into the text box (push-to-talk, not SAM's own Whisper pipeline) |
| `app.js` | Wires everything together: submit, cancel, retry, render loop |

## Phase 1 scope (what actually works)

- Text task submission → real SAM execution → result on phone
- Live execution progress via SSE (received → understanding → planning →
  executing → verifying → completed/failed/cancelled)
- Cancel (interrupts the actual running task, not just the UI)
- Retry (resubmits as a fresh task)
- Camera and voice **entry points** exist and are wired, but a captured
  photo is not yet sent to SAM — submitting an `image`/`image+voice` task
  today returns an honest "not supported until Phase 2" failure instead
  of silently ignoring the photo. See `docs/iqoo/PROGRESS.md`.

## Not yet built (Phase 2)

- Actually uploading the captured image as a task attachment
- Vision adapter → structured schema context
- Server-side STT for real (non-browser) voice capture
- The whiteboard-to-backend demo workflow
