# SAM × iQOO Hackathon 2026 — Engineering PDR (reference copy)

This file is a reference summary of the authoritative PDR
(`Runtime_Rebels_SAM_iQOO_2026_PDR.docx`, v1.0) that governs this branch.
The original docx is the source of truth if anything here drifts from it.

**Team:** Runtime Rebels | **Track:** Productivity | **City:** Hyderabad
**Event:** iQOO Hackathon 2026, September 26–27, 2026
**Branch:** `hackathon/iqoo-2026`

## One-line proposition

SAM turns the iQOO phone into a multimodal sensory and control head for
autonomous execution on the connected PC.

## Core loop

```
SEE → UNDERSTAND → PLAN → EXECUTE → VERIFY → REPORT
```

## Architecture rule

Add thin adapters around the existing SAM Brain, Planner, ReAct, Memory,
Hands, and Verification systems. Do not duplicate or rewrite them.

## Phases

1. **Phone Surface & Execution Gateway** — minimum vertical slice:
   Phone → SAM → existing execution engine → Phone result.
2. **Multimodal Phone-to-PC Intelligence** — camera + voice become SAM's
   actual sensory head; primary demo is whiteboard schema → tested
   FastAPI backend.
3. **Competition Reliability & Demo System** — connection recovery,
   execution safety, demo reset infrastructure, ≥9/10 successful
   end-to-end runs.

## Full requirements

See the attached PDR document and the original implementation prompt for
the complete, authoritative specification (task contract, event schema,
Office Kit architecture rule, reliability targets, stop/escalation
conditions, and definition of done). This file intentionally does not
restate every clause — `ARCHITECTURE.md`, `PROTOCOL.md`, and
`TEST_PLAN.md` in this directory cover the parts that are actually
implemented, phase by phase.
