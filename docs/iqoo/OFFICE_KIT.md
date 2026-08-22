# iQOO Branch — Office Kit

## What Office Kit is (per the implementation prompt)

The event-provided phone↔PC interconnectivity mechanism: screen
mirroring, shared clipboard, file transfer, remote control. Used during
**Red Light** (phone-first, laptop restricted, interaction only through
Office Kit) and available during **Green Light** (phone + laptop both
free).

## What SAM does and does not assume

SAM does **not** implement, replace, or bypass Office Kit. This branch
adds one thing on top of whatever Office Kit provides: an HTTP+SSE
surface (`iqoo/server.py`) that a browser can reach.

```
iQOO PHONE
    │  (however Office Kit connects phone↔laptop during the actual event)
    ▼
Office Kit
    ▼
Laptop network interface
    ▼
iqoo/server.py  (http://<laptop-ip>:8420)
    ▼
SAM
```

During development (this repository, pre-event), "Office Kit" is
simulated by same-WiFi HTTP access — a phone browser hitting
`http://<laptop-ip>:8420/` directly. This is a reasonable stand-in
because Office Kit's job (per the prompt) is providing phone↔PC
connectivity and screen mirroring; it is not expected to change SAM's
own HTTP contract, only the transport the phone uses to reach it.

## Stated but unverified assumptions (flag before the event)

The following are assumptions this branch makes because the actual
Office Kit behavior is not available to inspect in this environment.
Per the implementation prompt's stop conditions, these must be verified
against the real event-provided kit before the competition, not assumed
away:

1. **Office Kit's mirrored browser can reach an arbitrary local port
   (8420) on the laptop.** If Office Kit only mirrors a specific browser
   tab/app rather than proxying arbitrary local traffic, the phone client
   may need to be opened *through* whatever Office Kit's own launch
   mechanism is, not typed as a raw URL.
2. **SSE (`text/event-stream`) survives whatever Office Kit's screen
   mirroring / clipboard bridge does to network traffic.** If Office Kit
   introduces a proxy that buffers responses, the heartbeat comments in
   `PROTOCOL.md` may not be sufficient — this needs a live test with the
   actual kit.
3. **Red Light's "laptop restricted" rule does not prohibit the laptop
   from running a local server process** (as opposed to prohibiting a
   human from operating the laptop directly). This branch assumes the
   restriction is on human interaction with the laptop, not on the
   laptop computing at all — SAM's entire premise requires the laptop to
   execute autonomously during Red Light.

**Per the implementation prompt's stop conditions: if Office Kit's
actual behavior contradicts any of the three assumptions above, this is
a STOP condition, not something to guess past.** Verify against the
official rules and the real kit before the event, and escalate here if
any assumption breaks.

## What Phase 1 has NOT tested

Everything in this document is architectural reasoning, not a verified
result — Phase 1 was built and tested entirely offline (see
`TEST_PLAN.md`). No real Office Kit hardware or event ruleset was
available to test against.
