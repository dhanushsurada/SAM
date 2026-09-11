# iQOO Branch — Demo

## Phase 2 demo — whiteboard to backend (the PDR's primary demo)

```
1. python -m iqoo.server                    # on the laptop
2. open http://<laptop-ip>:8420/            # on the phone, same WiFi
3. Tap camera, photograph a schema (paper/whiteboard)
4. Tap mic, say "Turn this into a tested FastAPI backend on my PC"
   (Phase 2 client note: real server-side voice capture and the
   camera-attachment submission UI are described as built in this
   phase's code — see "What Phase 2 has NOT been run against" below for
   what's untested vs. what's implemented.)
5. Submit — input_type becomes "image+voice"
6. Watch: received → understanding → perceiving → planning → executing
   → verifying → completed
7. During "perceiving": SAM's vision model reads the photo, SAM's
   Whisper pipeline transcribes the voice note
8. During "planning"/"executing"/"verifying": the SAME unmodified
   Planner/ReAct/Hands/Verifier from Phase 1 (and from main.py) do the
   actual work — nothing about them changed
9. Phone shows the real result text from actual execution — never a
   hardcoded "Build verified — tests passed."
```

This is the literal architecture described in PERCEPTION.md: the photo
and voice note become a single enriched text instruction, which the
unmodified Brain/Planner/ReAct pipeline then acts on exactly as if it
had been typed.

## What Phase 2 has NOT been run against

- **No real Ollama vision model call** (moondream/llava) has been made
  in this environment — `VisionAdapter` was tested only against mocked
  HTTP responses (`tests/test_iqoo_phase2_offline.py`).
- **No real faster-whisper transcription** has been performed —
  `AudioAdapter` was tested only against a mocked model object.
- **No real iQOO camera or microphone** was used to produce a test
  image/audio file — all test fixtures are synthetic byte strings that
  merely pass MIME/size validation, not real decodable media.
- **No real Office Kit hardware** — same untested-assumptions list as
  `OFFICE_KIT.md`.

Per the Phase 2 instructions: do not claim real-device validation
anywhere until the actual Mac + iQOO device + Ollama + event toolkit are
available and this workflow is run end to end for real.

## Phase 1 demo (unchanged, still works)

```
1. python -m iqoo.server           # on the laptop
2. open http://<laptop-ip>:8420/   # on the phone, same WiFi
3. Type an instruction (e.g. "open Safari and go to github.com")
4. Tap "Send to SAM"
5. Watch the phase checklist light up: received → understanding →
   planning → executing → verifying → completed
6. See the real result text SAM produced
7. Tap "Cancel" mid-run on a longer task to prove the interrupt is real,
   not cosmetic
8. Tap "Retry" on a finished task to resubmit it
```

This proves the full contract in section 18 of the implementation
prompt for the **text** path: Phone → SAM → existing execution engine →
Phone result, with live progress and real cancellation.

## What this demo does NOT show yet

- Any Office Kit hardware (Phase 1+2 were built and tested on same-WiFi
  HTTP only — see `OFFICE_KIT.md` for the untested assumptions).
- Reliability infrastructure: seeded environment, 10-run regression
  (Phase 3). Demo reset itself now exists — see below — these two don't.
- Real hardware validation of any kind — see "What Phase 2 has NOT been
  run against" above.

## Repeatability (Phase 1)

Each task submission is a fresh `task_id` — running the same instruction
twice never corrupts shared state (verified in
`tests/test_iqoo_phase1_offline.py::test_gateway_retry` and
`::test_api_endpoints`). `POST /api/iqoo/demo/reset` (Phase 3A; see
`PROTOCOL.md`) clears all task/event state between runs — call it
directly; there's no separate CLI/script wrapper, and none is needed for
a single `curl` call before a demo run.
