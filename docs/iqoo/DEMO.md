# iQOO Branch — Demo

## Phase 1 demo (what's real today)

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

- The camera capturing a physical whiteboard schema and SAM acting on it
  (Phase 2 — the PDR's primary demo).
- Voice going through SAM's own Whisper pipeline (Phase 1's mic button is
  browser dictation into the text box, not a server-side STT call).
- Any Office Kit hardware (Phase 1 was built and tested on same-WiFi
  HTTP only — see `OFFICE_KIT.md` for the untested assumptions).
- Reliability infrastructure: demo reset, seeded environment, 10-run
  regression (Phase 3).

## Repeatability (Phase 1)

Each task submission is a fresh `task_id` — running the same instruction
twice never corrupts shared state (verified in
`tests/test_iqoo_phase1_offline.py::test_gateway_retry` and
`::test_api_endpoints`). There is currently no dedicated "reset the demo
environment between runs" script; that's explicitly Phase 3
(`hackathon/demo/`) scope.
