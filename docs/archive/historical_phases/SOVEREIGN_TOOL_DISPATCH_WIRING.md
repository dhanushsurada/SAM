# Sovereign Tool-Dispatch Wiring (SIH26117 Milestone 3)

Status: done. The gap flagged as out of scope in
`docs/PHASE_1_CONSOLIDATION_REGRESSION_REPAIR.md` ("What this pass
surfaced but did not fix") — now fixed, on request, as its own pass.

## What was missing

`agent/react_loop.py`'s `execute()` had zero dispatch for
`read_document`, `search_knowledge`, `calculate`, or `create_document`.
The tools themselves were already fully built and unit-tested
(`sovereign/tools/*.py`, confirmed passing via `test_sovereign_tools_
offline.py` before this pass even started) — only the wiring into the
ReAct loop's dispatch table was gone. `sovereign/tools/__init__.py`'s
own docstring named the exact missing pieces unprompted: *"See
agent/react_loop.py's `_execute_read_document` /
`_execute_search_knowledge` / `_execute_calculate` /
`_execute_create_document` for how the agent invokes these"* — methods
that didn't exist. Same pattern as `run_task_with_optional_sovereign_
mode` in the prior pass: a capability built and tested standalone, with
only its connection to the rest of the system lost.

## What changed

**`agent/react_loop.py`:**
- `ReactLoop.__init__` gains `self._knowledge_index = None` and a new
  `_get_knowledge_index()` lazy loader (`VectorIndex(self.settings)`),
  following the exact existing pattern of `_get_control()` /
  `_get_browser()` / `_get_terminal()` / `_get_vision()` — same
  caching, same lazy import style. Construction never raises even
  without `chromadb` installed (`VectorIndex.__init__` already catches
  `ImportError` internally); every consumer already checks `.available`
  or degrades to a safe no-op, so passing a real (possibly-unavailable)
  index into both `read_document` and `search_knowledge` is exactly the
  tools' own designed-for case, not a workaround.
- `execute()` gets four new dispatch branches
  (`read_document`/`search_knowledge`/`calculate`/`create_document`),
  each calling straight into the matching `sovereign/tools/*` function
  with a lazy, method-local import — consistent with every other Hands
  tool in this file, and keeps `react_loop.py` importable regardless of
  which optional extras (`python-docx`, `chromadb`, `reportlab`) happen
  to be installed.
- Each tool's own exception type (`CalculationError`,
  `DocumentCreationError`, a missing-file error from `read_document`)
  is deliberately left to propagate to `execute()`'s existing outer
  `try/except` rather than caught locally — the same `"Error executing
  {action}: ..."` wrapping every other action already gets, so
  `agent/verifier.py` needed zero changes to recognize a failure from
  any of these, exactly as `test_sovereign_agent_integration_offline.py`
  itself verifies.

**`core/brain.py`:** `SYSTEM_PROMPT` now lists all four as top-level
`action` values (they're peers of `control`/`browser`/`terminal`/
`vision`, not subtypes of `control`), documents an example payload for
each, adds a "Read local documents, search indexed document knowledge,
do arithmetic, and generate Word documents" capability line, and
reinforces — in the model's own global instructions, not just per-
document via `sovereign/security/document_trust.py`'s existing
`wrap_untrusted()` — that document content is data to analyze, never
instructions to follow. Every Phase 3 addition to this same prompt
(`open_app`/`hotkey`/`screenshot`, the verb-stripping guidance) is
untouched and still verified by its own tests.

## What did not change

`sovereign/tools/*.py`, `sovereign/knowledge/`, `sovereign/security/
document_trust.py`, `agent/verifier.py` — none of it. This was
purely a wiring gap, not a missing-capability one; nothing about how
any of these tools work needed to change, only whether the ReAct loop
knew to call them.

## Testing

Before this pass: `test_sovereign_agent_integration_offline.py` and
`test_sovereign_e2e_offline.py` both failed (every planned step
reporting `"Unknown action: read_document"` etc.). After:

- `test_sovereign_agent_integration_offline.py`: **17/17**, including
  the security-critical case — `calculate("__import__('os')")` is
  rejected by the existing `ast`-based evaluator (never reaches
  `eval()`) and wrapped exactly like any other tool error.
- `test_sovereign_e2e_offline.py`: **35/35** — the full
  "confidential-industrial-inspection" scenario now runs completely:
  reads two real fixture documents (a PDF and a DOCX), indexes them,
  searches the index, runs a real calculation, generates a real
  Approval Note `.docx` with all required sections and preserved
  source evidence, blocks a simulated network-exfiltration attempt
  while the legitimate task still completes, and confirms zero
  external connections were made.
- Full 39-file offline suite, re-run clean with each file's own
  documented `HOME=` isolation: **exactly these two files flip from
  FAIL to PASS; every other file is byte-for-byte identical** to the
  prior (Phase 1 consolidation) state — including `test_hands_
  reliability_offline.py` (73/73) and `test_hands_phase3_reliability_
  offline.py` (81/81), both re-verified unchanged despite this pass
  touching the same two files (`react_loop.py`, `brain.py`) Phase 3
  also modified.

Zero regressions.

## Known, pre-existing, not touched

`test_sovereign_agent_integration_offline.py`'s own
`test_verifier_known_limitation_document_content_can_false_positive`
documents (and this pass leaves exactly as documented, not fixed):
`agent/verifier.py` does a substring scan across the *whole*
observation, including embedded document text — so legitimate document
content that happens to contain a phrase like "could not find" reads as
a failure. Pre-existing (already true for browser/vision observations
before this pass), not introduced by this wiring, and fixing it means
editing `agent/verifier.py` — outside this pass's scope.
