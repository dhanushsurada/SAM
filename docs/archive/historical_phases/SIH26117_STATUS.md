
# SIH26117 — Implementation Status

**Problem statement:** SIH26117 — "Sovereign On-Premise Agentic AI Workbench
using Open-Weight Multimodal LLMs for Confidential Industrial Work"
**Product identity:** VEDA — Sovereign Industrial AI Workbench (user-facing).
SAM remains the underlying engineering/repository identity and is not
renamed for branding — see `memory/identity.py`.
**Branch:** `sih26117`
**Last reconciled:** 2026-09-04, against the M6.2 commit.

This document maps the SIH26117 requirement to what's actually implemented,
with the evidence for each claim. Where something can't be backed by
evidence gathered in this environment, that's stated explicitly rather than
assumed. Code and test results are authoritative — nothing here should be
read as a claim beyond what's below.

---

## Status at a glance

| Milestone | Area | Status |
|---|---|---|
| M0 | Foundation / branch setup | Done |
| M1 | Document ingestion | Done |
| M2 | Local knowledge / RAG | Done |
| M3 | Agentic tools | Done |
| M4 | Deliverable generation | Done |
| M5 | Sovereignty / network guard | Done |
| M6 | End-to-end SIH workflow | Done |
| M6.1 | Runtime identity (VEDA) | Done |
| M6.2 | Model selection | Done |
| M7 | Documentation | In progress — this document is a slice of it |
| M8 | API + UI/UX | Separate workstream, not covered here |
| Final validation | — | Pending |
| Product freeze | — | Pending |

## M1 — Document ingestion
`sovereign/ingestion/` (`extract.py`, `chunk.py`, `pipeline.py`). PDF, DOCX,
TXT, and images (via Ollama vision). Extraction → structured content →
chunks → provenance metadata.
**Evidence:** `tests/test_sovereign_ingestion_offline.py` — 45/45, re-run 2026-09-04.

## M2 — Local knowledge / RAG
`sovereign/knowledge/` (`vector_index.py`, `retrieval.py`) plus shared
`core/embeddings.py`. Local ChromaDB, dedicated `sam_documents` collection
kept separate from the existing `sam_memory` collection.
**Evidence:** `tests/test_sovereign_knowledge_offline.py` — 20/20, re-run 2026-09-04.
**Open caveat, carried forward unresolved:** these are offline/fake-client
tests. The real ChromaDB `PersistentClient`/upsert/query path has not been
validated against an actual ChromaDB install in any environment available
during this work.

## M3 — Agentic tools
`sovereign/tools/` (`read_document`, `search_knowledge`, `calculate`,
`create_document`) plus `sovereign/security/document_trust.py`.
`calculate.py` uses a safe AST evaluator — no `eval()`/`exec()`. Retrieved
document content is explicitly labeled and treated as untrusted; this is
defense-in-depth, not a mathematical guarantee against prompt injection.
**Evidence:** `tests/test_sovereign_tools_offline.py` — 55/55;
`tests/test_sovereign_agent_integration_offline.py` — 17/17. Both re-run 2026-09-04.

## M4 — Deliverable generation
`create_document` produces a real Approval Note (`.docx`): title, generated
timestamp, source documents, sections, evidence blocks with source/location
and supporting quotations. Produced by the real ReactLoop, not a standalone
unit-level demo.
**Evidence:** covered within the M3 tools suite above (55/55).

## M5 — Sovereignty / network guard
`sovereign/security/network_guard.py`. `SocketGuard` monkey-patches
`socket.socket.connect` process-wide for the guarded task: allows loopback,
the configured Ollama host, and an explicit allowlist; blocks everything
else; records evidence. `psutil`-based subprocess connection snapshots are
defense-in-depth for subprocess visibility.
**Not an air-gap guarantee** — it's software enforcement. A genuinely
air-gapped deployment also needs OS/network infrastructure controls; this
doesn't substitute for those.
**Evidence:** `tests/test_sovereign_network_guard_offline.py` — 24/24, re-run 2026-09-04.

## M6 — End-to-end SIH workflow
Documents → ingestion → local knowledge → agent (read/search/calculate) →
synthesis → Approval Note → sovereignty evidence, exercised as one real flow.
**Evidence:** `tests/test_sovereign_e2e_offline.py` — 35/35, re-run 2026-09-04.
`tests/test_sovereign_e2e_live.py` needs a real Ollama, not available in any
environment used for this work — it correctly reports "Insufficient data —
not verified in this environment" rather than a false pass or fail;
confirmed by running it 2026-09-04.

## M6.1 — Runtime identity (VEDA)
`Identity.assistant_name` (`memory/identity.py`) is the single persisted
source of truth, defaulting to "VEDA" on a fresh install. First-run flow:
name, then (as of M6.2) real model selection, then normal startup. The
`--name` CLI flag (process-local) and the runtime `name X` command
(persists) both route through this one field.
**Evidence:** `tests/test_identity_setup_offline.py` — 42/42, re-run 2026-09-04.

## M6.2 — Model selection
`Settings.model_explicitly_set` (`config/settings.py`) guards
`Settings._select_model()`: RAM-based auto-detection now only supplies a
default when no explicit choice has been made, and can no longer silently
overwrite a persisted choice. This was a real, reproducible bug in the
pre-M6.2 code — confirmed empirically before the fix, then fixed and
re-verified. `Brain.list_installed_models()` (`core/brain.py`) is a new,
read-only discovery method. First-run Step 2 and a new runtime `model X`
command both offer a real choice from Ollama's actually-installed models,
falling back to the original M6.1 readiness-check behavior when Ollama is
unreachable or has nothing installed. Nothing here ever calls `ollama pull`.
**Evidence:** `tests/test_model_selection_offline.py` — 46/46 checks across
23 functions, 2026-09-04. Full existing suite re-run alongside it with zero
regressions.

## Cross-cutting caveats that apply to the whole submission

- **No pytest anywhere in this repo's test evidence.** Every count above
  comes from directly running the repo's own test scripts
  (`python3 tests/test_X.py`) — the project's own convention, not pytest.
  Worth saying plainly in a demo Q&A rather than letting it look like a
  pytest run.
- **One known, pre-existing, unrelated test failure:**
  `tests/test_founder_mode_live.py` (3/7), because it needs a live Ollama
  backend for LLM auto-capture. Reproduced 2026-09-04. Not connected to
  SIH26117 work and intentionally not "fixed" as part of it, per regression
  discipline.
- **Real Ollama/ChromaDB validation is still owed.** Every offline suite
  above has been independently re-run and passes; the interactive,
  real-model, real-vector-store path needs a pass on the actual dev/demo
  machine before the live SIH demonstration.
- **Product identity:** the SIH judge should experience "VEDA — Sovereign
  Industrial AI Workbench." SAM is the underlying engineering/repository
  identity and isn't user-facing in the SIH product surface. Internal
  architecture, classes, and the repository itself are not renamed for
  branding.

## What M7 still needs (not covered by this document)

- Architecture write-up / diagram
- Demo procedure for the live SIH demonstration
- Installation/configuration walkthrough reflecting M6.2's model selection
- Submission/deck support material
- README reconciliation for the SIH-specific (VEDA) surface — the current
  `README.md` documents the general SAM product, not the SIH26117/VEDA
  workbench specifically

This document intentionally doesn't touch `docs/ROADMAP_STATUS.md` (last
reconciled 2026-08-21) — that file tracks a separate, pre-SIH roadmap for
the general SAM product (feature tiers, Telegram bridge, memory
architecture). Mixing the two would blur two genuinely different tracks.
