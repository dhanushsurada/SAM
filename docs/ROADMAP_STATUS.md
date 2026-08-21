# SAM Roadmap Status

**Last reconciled:** 2026-08-21  
**Repository:** `dhanushsurada/SAM`

This document reflects the implementation present in the repository. Code and
tests are authoritative; older roadmap statements that conflict with the
current implementation should not be treated as current status.

---

## 1. Completed Foundations

| Area | Status | Notes |
|---|---|---|
| Phase 0 — Founder Mode v2 | ✅ Complete | Persistent decisions, preferences, rejections, confidence, review |
| Phase 1 — Planner + Reflection | ✅ Complete | Planning, fallback execution, stored lessons |
| Phase 1.5 — Verification + Reflection | ✅ Complete | Retry/abort, mistakes, metrics, reflection bridge |
| ReAct execution | ✅ Complete | Bounded loop with stagnation detection |
| Persistent memory | ✅ Complete | SQLite episodic + ChromaDB semantic retrieval |
| Latency fixes | ✅ Complete | Redundant Brain calls and repeated failed TTS attempts reduced |
| Concurrency / vision safeguards | ✅ Complete | Serialized turns and `(0,0)` false-positive protection |
| Browser thread-affinity recovery | ✅ Implemented | Reactive recovery path present; environment-specific validation may require Playwright |
| Phase 2 — Telegram Bridge | ✅ Implemented | Pairing, trust, revocation, remote SAM interaction |
| Phase 3 — Offline licensing client | ✅ Implemented | Signed-license schema, verification, expiry/tamper handling |
| Feature-tier gating | ✅ Implemented | Memory retention, Founder Mode, and Incognito enforcement |

---

## 2. Feature-Tier Gating — Current State

Feature-tier gating is **implemented**. The licensing layer is no longer only a
trust mechanism; the resolved tier now affects application behavior.

### Free tier

- Memory retrieval is limited to **7 days**.
- Founder Mode capture is blocked.
- Founder Mode context is blocked.
- Incognito is restricted.

### Pro tier

- Memory retention is unlimited.
- Founder Mode is available.
- Incognito is available.

### Development mode

When `license_enforcement_enabled=False`, SAM resolves to full-access behavior
for development. This prevents local development from being locked out by an
unfinished licensing configuration.

### Enforcement paths

Tier resolution is consumed by:

- `memory/store.py`
- `memory/retrieve.py`
- `founder_mode/manager.py`
- `main.py`
- `ecosystem/telegram_bridge.py`

The dedicated tier test suite is:

```text
tests/test_feature_tier_offline.py
```

The detailed implementation specification is:

```text
docs/FEATURE_TIER_GATING.md
```

---

## 3. Telegram Bridge — Scope

The Telegram Bridge is implemented as a **remote interaction bridge**.

Current path:

```text
Phone
  ↓
Telegram
  ↓
Telegram Bridge
  ↓
Device Registry / trust check
  ↓
SAM turn
  ↓
Memory → Brain → ReAct → Hands
  ↓
Telegram response
```

Implemented:

- one-time pairing tokens
- token expiry
- trusted-device registry
- device revocation
- trusted/untrusted chat handling
- Telegram turn processing
- typing indicator
- tier-aware memory retrieval

### Not implemented

The Telegram Bridge should **not** be described as native device synchronization.

Still outside the current implementation:

- same-Wi-Fi device discovery
- direct phone↔computer transport
- shared conversation-state synchronization
- clipboard synchronization
- local file synchronization
- native mobile SAM client
- general-purpose device mesh

These remain later ecosystem work.

---

## 4. Current Memory Architecture

```text
User / Telegram request
        ↓
     Session
        ↓
      Brain
        ↓
    ReAct loop
        ↓
  ┌─────┴─────┐
  │           │
SQLite     ChromaDB
episodic   semantic
memory      memory
  │           │
  └─────┬─────┘
        ↓
 Tier-aware retrieval
```

Free-tier retention is applied at retrieval rather than merely hiding old
results after retrieval.

---

## 5. Next Milestone

### Sensitive-data redaction

**Status: 🔲 Pending**

The redaction module must be present and, more importantly, wired into every
relevant persistence path.

Required acceptance criteria:

1. Sensitive values are identified before persistence.
2. Founder Mode evidence is redacted before storage.
3. Memory save paths are redacted before storage.
4. Existing non-sensitive data remains usable.
5. Redaction failures fail safely rather than silently persisting raw secrets.
6. Dedicated regression tests cover the persistence boundaries.
7. Full regression suite passes.
8. A new checkpoint ZIP is produced before the work is considered delivered.

---

## 6. Remaining Engineering Backlog

| Item | Status |
|---|---|
| Sensitive-data redaction + persistence wiring | 🔲 Next |
| Reflection lessons → Brain prompt | 🔲 Pending |
| Browser-tool vs blind-click selection bias | 🔲 Pending |
| Formal interrupt/cancel regression test | 🔲 Pending |
| Scheduled / automated tasks | 🔲 Pending |
| Document ingestion | 🔲 Pending |
| Native same-Wi-Fi device pairing | 🔲 Future |
| Native mobile application | 🔲 Future |
| UI/UX specification and implementation | 🔲 Pending specification |
| Production SAM Infrastructure deployment | 🟡 Separate deployment milestone |

---

## 7. Validation Policy

Every completed engineering milestone should produce all four artifacts:

1. **Working code**
2. **Dedicated regression tests**
3. **Updated documentation**
4. **A fresh checkpoint ZIP**

A milestone is not considered checkpointed until the ZIP exists and contains
the complete updated source tree.

This policy is intentional: it protects the project against filesystem/session
loss and makes recovery reproducible.

---

## 8. Current Bottom Line

SAM has moved beyond the original prototype into an integrated autonomous-agent
stack with:

- local Brain / Ollama
- persistent memory
- Founder Mode
- planning
- ReAct execution
- verification and reflection
- browser, vision, control, and terminal hands
- Telegram remote access
- offline licensing
- feature-tier enforcement

The immediate engineering priority is **sensitive-data redaction at the actual
persistence boundaries**, followed by the remaining reliability and capability
work listed above.

Native phone↔computer synchronization and the mobile application are **not**
currently complete and should not be represented as completed features.
