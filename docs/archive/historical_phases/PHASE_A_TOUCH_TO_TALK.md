# Voice Phase A — touch-to-talk on the desktop app

**Status:** Phase A is complete in code and tests. It has been run end to end
in a Linux sandbox with the speech engines stubbed (section 7); it has **not**
been run with the real Whisper / Kokoro / Piper engines or inside the real
Tauri web views (WKWebView, WebView2, WebKitGTK). Section 8 is the checklist
for that.

Phase A of the voice plan gives the desktop app a microphone button: click,
speak, click again. SAM shows what it heard, does the task, and speaks the
answer. Phases B–D (wake word, hands-free conversation, phone) are not part
of this change.

## 1. What it is, and what it is not

It is the existing SAM pipeline with a voice front and back end. A recording
is an ordinary `audio` attachment on an ordinary task, so the Brain, Planner,
ReAct loop, Hands, verification, the task list and Cancel behave exactly as
they do for a typed message. There is no second agent and no second task
path.

- Speech in: Whisper (`ears/stt.py`, via the existing `AudioAdapter`).
- Speech out: SAM's own voice (Kokoro, then Piper, from `mouth/tts.py`).
- Only replies to **voice** messages are spoken. Typed messages stay silent.
- The legacy wake-word loop (`main.py`, openWakeWord, PyAudio) is untouched.

## 2. How it works

```
 mic ── getUserMedia + MediaRecorder (the app's web view)
  │      interfaces/desktop/src/features/voice/recorder.ts
  ▼
 POST /api/iqoo/tasks   input_type "voice", one "audio" attachment (existing contract)
  │
  ▼
 TaskGateway._perceive ── AudioAdapter.transcribe ── ears/stt.py (faster-whisper)
  │                         └─ new event: phase "perceiving",
  │                            message "Heard your voice message",
  │                            data {"transcript": "..."}
  ▼
 Brain / Planner / ReAct / Hands / verification            (unchanged)
  │
  ▼  the task reaches completed or failed
 POST /api/speech {"text": reply}  ── Kokoro, then Piper ──> WAV     (new, loopback only)
  │
  ▼
 played by the web view (Web Audio), so Stop is immediate
   └─ if SAM's voice cannot return audio: the web view's own speech synthesis
```

The desktop side is split so the behaviour can be tested without a browser:

| File (`interfaces/desktop/src/features/voice/`) | Role |
|---|---|
| `voiceMachine.ts` | Pure state machine: idle, starting, listening, sending, working, speaking, error. |
| `voiceController.ts` | Runs the machine: record, send, wait, speak, Stop. Ignores results that arrive after Stop. |
| `recorder.ts` | Microphone + `MediaRecorder`; always releases the mic; strips codec parameters from the MIME type (the server matches it exactly). |
| `player.ts` | Plays the WAV through Web Audio; the audio context is unlocked inside the click (WebKit only allows sound after a gesture). |
| `speak.ts`, `webviewVoice.ts`, `speechText.ts` | Picks SAM's voice or the web view's; cleans markdown; speaks at most ~600 characters and says where the rest is. |
| `voiceText.ts`, `taskLabel.ts` | The words shown; voice tasks are labelled by what SAM heard, never "(voice command)". |
| `VoiceProvider.tsx`, `VoiceControls.tsx` | The React shell: mic button, speak toggle, status line, top-bar indicator with Stop. |

## 3. Using it

1. Click the microphone in **Chat**, in the **Command Center / Tasks**
   composer, or in the **Quick Assistant** window. The OS may ask for
   microphone access the first time.
2. Speak, then click the microphone again to send. Recording also ends by
   itself after 60 seconds; anything under 0.4 seconds is treated as a stray
   click and explained, not sent.
3. SAM shows what it heard (the task is labelled with the transcript), works
   on it, and speaks the reply.
4. **Stop** (the same button or the Stop in the top bar) cancels whatever
   stage it is in: it discards a recording, abandons a pending
   voice request, silences speech, and cancels the voice task if it is still
   running. A message that was already on its way when you pressed Stop is
   withdrawn, so SAM does not act on a command you took back.
   Esc cancels voice work in the main window unless focus is in a text field,
   select, or dialog that handles Escape. In Quick Assistant it dismisses the
   window, stops capture or playback, and lets an already-submitted task
   continue.
5. The speaker button next to the microphone turns spoken replies off; the
   choice is remembered.

Anything that goes wrong is shown in the status line in plain words (no
microphone, permission refused, nothing heard, speech-to-text not installed,
SAM not running) and the app stays usable.

## 4. First use: installing and downloading

Voice is optional and nothing is installed by default.

- **Diagnostics → Installation and recovery** now offers two groups that
  need no PyAudio: **speech-input** (`faster-whisper`) and **speech-output**
  (`kokoro`). The existing **voice** group (which adds PyAudio and
  openWakeWord for the wake-word loop) is unchanged. Before this change
  there was no way to get speech-to-text and text-to-speech without
  PyAudio, which has no wheel on some platforms.
- Installing a speech group takes effect immediately; SAM does not need a
  restart.
- The first transcription downloads the Whisper model and the first spoken
  reply downloads Kokoro's model. This needs internet once and can take a
  few minutes; the app says so after 8 seconds instead of looking frozen.
  After that everything runs locally.
- If a first-use download fails (offline), a transcription failure is
  explained and retried on the next message. SAM's voice is retried after
  60 seconds; until then the web view uses a fallback only if the OS reports
  a local voice. Otherwise the reply remains on screen.
- Until speech-input is installed the microphone button is disabled and
  says how to fix it. Until speech-output is installed (or if it cannot
  speak) replies use a web-view voice only when the OS reports it as local;
  otherwise SAM leaves the reply on screen. A one-time notice explains the
  local fallback. If `tts_engine` is `none` in SAM's settings, replies are not
  spoken at all (the desktop Settings page does not offer `none`; use the
  speaker button next to the microphone).

## 5. Data handling

Voice recordings are sent as audio attachments through the existing task
API. The current task store keeps those attachments as base64 in
`~/.sam_data/iqoo/tasks.db`; task reads return the attachment, and this phase
does not delete it after transcription. The API defaults to `0.0.0.0`; task
authentication is optional and off unless configured, and the HTTP API does
not provide transport encryption. Use voice tasks only on a trusted machine
and network until task authorization, secure transport, and an audio-retention
policy are in place.

## 6. API changes

### `POST /api/speech` (new)

Loopback callers only (`403` from the LAN), like the other desktop-initiated
routes. Not under `/api/iqoo/`: the phone-task contract is unchanged.

Request: `{"text": "..."}`, 1 to 2000 characters. Markdown is stripped before
speaking.

| Status | Meaning | The desktop app |
|---|---|---|
| `200` | `audio/wav`, mono 16-bit, `Cache-Control: no-store` | plays it |
| `409` | speech is turned off (`tts_engine: none`) | stays silent |
| `422` | empty body, over the length limit, or nothing speakable (including text that has no words in it, such as a lone emoji, which a working engine cannot voice; that does not count against the engine) | stays silent |
| `501` | no installed engine can return audio (nothing installed, a failed first-use download, or `tts_engine: system`); the detail names each engine with a fixed reason (`not installed`, `timed out` or `failed`), never the engine's own error text, which can hold file paths and goes to SAM's log only | uses the web view's voice |
| `403` | not a loopback caller | — |

### Heard-transcript event (new)

After transcription the gateway publishes, on the existing task event
stream (`GET /api/iqoo/tasks/{id}/events`):

```json
{"type": "event", "task_id": "...", "seq": 3, "phase": "perceiving",
 "message": "Heard your voice message", "timestamp": "...",
 "data": {"transcript": "what time is it"}}
```

`data` appears only on events that are given one; every other event has
exactly the shape it had before. The stored task still has the instruction
`(voice command)`; the transcript is delivered by this event and is not
persisted.

## 7. What changed

**Server**

| File | Change |
|---|---|
| `compatibility/manifest.json`, `runtime/environment_manager.py` | New dependency groups `speech-input` and `speech-output`, reported with the other capabilities. |
| `mouth/tts.py` | `TextToSpeech.synthesize_wav(text) -> bytes` for Kokoro and Piper; `TTSUnavailableError` / `TTSDisabledError`. The Kokoro and Piper code was split into "render" and "play" so `speak()` renders and plays exactly what it did. A failed engine is retried after 60 s (`SYNTH_RETRY_SECONDS`); an engine that only had nothing to say for one text (no audio, or a WAV with no sound) is not counted as failed. A Piper file that is not a readable WAV is rejected instead of being passed on. `speak()` keeps its skip-for-the-rest-of-the-run rule. |
| `interfaces/api/server.py`, `schemas.py` | `POST /api/speech`; one shared `TextToSpeech`; it is reset after a successful dependency repair so a newly installed engine works at once. |
| `interfaces/api/events.py`, `gateway.py` | `EventBus.publish(..., data=None)`; the gateway publishes the transcript. |
| `multimodal/audio/adapter.py` | Two first-use fixes that voice depends on: a model load that failed (the first-use download) is no longer cached as a half-built instance, and the load error is reported as a readable `PerceptionError`; `faster-whisper` installed after SAM started is picked up without a restart. |

**Desktop**

New: `src/features/voice/` (above) and `src/services/speech.ts`. Edited to
host the controls: `App.tsx`, `layouts/TopBar.tsx`, `features/chat/*`,
`features/iqoo/{TaskComposer,ActiveTask,SessionTaskList}.tsx`,
`features/command-center/RecentTasks.tsx`,
`features/quick-assistant/QuickAssistantApp.tsx`, `stores/taskSession.tsx`
(`submitTask` returns the task; `cancelTask`; per-session transcripts),
`api/client.ts` (`synthesizeSpeech`), `api/types.ts`, `lib/file.ts`
(`blobToBase64`), `package.json` (`npm test`).

**CI** (`.github/workflows/ci.yml`): `numpy` added to the Python test
dependencies (the new TTS tests import it) and `npm test` runs after the
desktop build. The job names are unchanged.

## 7a. Tests added

- `tests/test_tts_synthesis_offline.py`: WAV format and clipping, text
  cleaning, engine order, failure and retry, a text with nothing to voice
  versus a real engine failure, no file paths in what a caller is told,
  disabled and system voice, locking across threads, and that `speak()` is
  unchanged.
- `tests/test_speech_api_offline.py`: the HTTP contract of `/api/speech`
  (every status above, loopback only, no caching), the transcript event
  (and that other events are unchanged), the audio adapter's first-use
  behaviour, and the reset after a dependency repair.
- `tests/test_environment_manager_offline.py`: the new groups.
- `interfaces/desktop/src/features/voice/*.test.ts`: the state machine, the
  controller (including every Stop path and late results after Stop), the
  recorder, the player, speech selection, text cleaning and labelling.

## 8. What was verified, and how

Environment: Linux x86-64 sandbox, Python 3.13, Node 22, headless Chromium
(Playwright). No Mac, no Windows, no GPU, no Ollama, no model weights, no
internet beyond package registries.

**Run and passed**

- The new Python tests, and the whole existing suite compared with the
  original tree (section 10 has the commands; the final numbers are in the
  hand-over report, not here, so they cannot go stale in the repo).
- The desktop build (`tsc -b && vite build`, strict) and the frontend unit
  tests (`npm test`).
- Mutation checks: the new server, TTS and adapter logic, and the voice
  modules, were each deliberately broken in many small ways (a flipped
  comparison, a dropped call, a wrong status code). Every broken copy now
  makes a test fail; the ones that survived at first were killed by adding
  tests (or removing code nothing needed).
- A browser end-to-end run in headless Chromium against the **real** SAM API
  process and the production desktop build, covering a full spoken
  conversation, Stop at every stage (listening, transcribing, preparing the
  voice, speaking), a too-short recording, refused microphone permission,
  speech-to-text not installed, no SAM voice installed (web view fallback),
  spoken replies off (and surviving a reload), a silent recording, the top-bar
  indicator and Stop surviving navigation, a voice task named by what was
  heard, typed tasks staying silent, and a reply still being spoken after
  another task was selected.

**What was real in that browser run:** the FastAPI app, the loopback guard,
request validation, the gateway and its worker thread, the task database, the
event stream, `AudioAdapter`, `mouth/tts.py`, Chromium's `getUserMedia` (with
its fake microphone device), `MediaRecorder` encoding to Opus/WebM, and Web
Audio playback (instrumented to record start and stop).

**What was stubbed:** the Brain/ReAct loop (fixed reply text), the Whisper
model (returns a fixed transcript after checking it was handed real audio),
the Kokoro pipeline (returns a tone), and `speechSynthesis.speak` (records the
text instead of speaking). The permission-refused case was exercised by
emulating the browser's `NotAllowedError`; real headless Chromium has no
permission prompt, so it reports "Not supported", which is also handled.

**Not verified anywhere**

- Real Whisper, Kokoro or Piper output (never run in the sandbox; Kokoro does
  not install on the sandbox's Python).
- The Tauri shell: WKWebView (macOS), WebView2 (Windows), WebKitGTK (Linux).
  In particular whether each web view shows its microphone prompt, which
  `MediaRecorder` MIME type it produces (WKWebView typically produces
  `audio/mp4`, which the server accepts; decoding it was not tested), and
  whether `AudioContext` playback starts after a click.
- The Quick Assistant window (type-checked and built, but not mounted in the
  browser test).
- Closing or hiding the window while recording (the code stops the
  microphone on `visibilitychange` and `pagehide`; not exercised).
- Real latency, and a real person's voice.

## 9. Check on real hardware before relying on it

On each OS you ship for, with `speech-input` and `speech-output` installed
from Diagnostics:

1. Click the mic. The OS microphone prompt appears (macOS shows the text from
   `Info.plist`; the hardened-runtime build needs the audio-input entitlement
   that `Entitlements.plist` already declares). Allow it.
2. Say a short command. Watch for: the transcript appears; the task runs; the
   reply is spoken in SAM's voice. Note how long the first transcription and
   the first spoken reply take (model downloads).
3. Check that the transcript is right for whatever format that web view
   records (WKWebView typically records `audio/mp4`; Chromium-based ones
   `audio/webm`). A wrong or empty transcript on one OS only points at the
   format.
4. Press Stop in each stage, and Esc; confirm the OS "microphone in use"
   indicator goes off.
5. Turn the network off before the very first use, send a voice message, then
   turn it on and try again after a minute: the second attempt should work
   without restarting SAM.
6. Uninstall speech-output (or set the engine to `system`): replies should be
   spoken with the web view's voice and one notice shown.
7. Hide or close the window while listening: the microphone should be released.
8. Open the Quick Assistant (global shortcut) and repeat steps 1 to 4 there.

## 10. Known limits, and what is deferred

- **Stop does not interrupt the server's synthesis.** Stop aborts the
  request and silences playback at once, but a reply SAM is still rendering
  keeps running on the server, and the speech engine renders one request at
  a time, so the next speech request waits for it. The wait has no time limit
  (the first use also downloads the model, with no time limit either), and
  each waiting request holds one of the server's worker threads. How long an
  ordinary reply takes to render was not measured (no real engine ran in the
  sandbox). A real `TextToSpeech.stop()`, cancelling a request whose caller
  has gone, a wait limit, and barge-in belong to Phase B.
- **Installing any capability resets SAM's voice engine.** After a successful
  repair of any dependency group (not only `speech-output`), the speech engine
  is rebuilt, which is how a newly installed engine is noticed without a
  restart. The cost is that the next spoken reply loads the voice model again;
  if a repair finishes while a reply is being rendered, the old and the new
  engine can briefly both hold a model in memory.
- **The web view fallback is local-only.** The app selects a fallback voice
  only when the OS reports `localService`; otherwise spoken fallback is
  unavailable and the reply remains visible. With speech-output installed,
  SAM's reply is synthesized locally. Spoken replies can be turned off with
  the speaker toggle.
- **Audio is stored with the task.** The recording travels as a base64
  attachment, so it is saved in `~/.sam_data/iqoo/tasks.db` and returned by
  `GET /api/iqoo/tasks/{id}`. This is how attachments already worked; voice
  makes it a routine event.
- **The task API is open on the LAN.** `/api/iqoo/tasks` and its event stream
  (now including the transcript) are reachable from other devices on the
  network, as before this change; `/api/speech` is loopback only.
- Each task is independent: SAM does not see earlier messages from the screen
  (its memory carries context). Conversation history is Phase B.
- The transcript is not persisted: after a restart, an old voice task shows
  "Voice message" instead of what was said. It is also read from the task's
  event stream, which the app only follows for the selected task: if you
  select a different task before SAM has finished transcribing, the earlier
  voice task shows "Voice message" until you select it again. (Its reply is
  still spoken: task status is refreshed for all running tasks every 5
  seconds, so the reply can start up to 5 seconds late in that case.)
- The main window and the Quick Assistant are separate web views with
  separate voice state and audio output.
- Not built (later phases): wake word in the desktop app, hands-free
  listening and end-of-speech detection, interrupting SAM by speaking,
  Android capture and speech, and the "hey sam" wake phrase (the default is
  still `hey_jarvis`).
- Replies longer than about 600 characters are spoken in part, and SAM says
  the rest is on screen.

## 11. Running the tests

```bash
# Python (from the repository root)
python -m pytest tests/test_tts_synthesis_offline.py tests/test_speech_api_offline.py -q
python tests/test_environment_manager_offline.py        # script-style suite
python -m pytest tests -q --ignore=tests/test_founder_mode_live.py --ignore=tests/test_sovereign_e2e_live.py   # what CI runs

# Desktop (Node 22 or newer)
cd interfaces/desktop && npm ci && npm run build && npm test
```

Many older suites in `tests/` use a `check()` helper that records failures
without raising, so `pytest` reports them as passed whatever happens; run
them as scripts (`python tests/<file>.py`) to see their real result. The
Phase A Python tests are plain pytest functions with real asserts.
