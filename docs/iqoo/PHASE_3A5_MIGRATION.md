# iQOO Branch — Phase 3A.5: Architecture Migration

Status: code-complete and offline-verified; not committed (staged/unstaged
git state left as-is for review — see `git status` / `git diff --cached`).

## Why this phase exists

Phases 1–3A built the phone-task gateway, perception adapters, and
reliability layer entirely under `iqoo/`, plus a Telegram remote-control
bridge under `ecosystem/`. That was the right call while the shape of the
thing was still being discovered — but by Phase 3A, `iqoo/` had become a
permanent-looking top-level subsystem holding code that has nothing to do
with vivo/iQOO specifically (an SSE event bus, a Pydantic schema layer, a
vision/audio perception adapter, a SQLite task store). The PDR's own target
architecture (`ARCHITECTURE.md`'s eventual shape, and the PDR's Local Data
Separation / SAM Connect language) puts generic capabilities under SAM
proper and reserves a *bridge* for anything genuinely vendor-specific.
Phase 3A.5 closes that gap: it relocates each component to where it
actually belongs, and leaves `iqoo/`/`ecosystem/` as compatibility
boundaries instead of implementation owners.

This phase is a pure move. No behavior, schema, HTTP route, or on-disk data
path changed — see Compatibility below.

## What moved

| Old location | New (canonical) location | Why |
|---|---|---|
| `iqoo/gateway.py` | `interfaces/api/gateway.py` | Orchestration specific to the phone-task HTTP API (not reused by Telegram), so it lives under that interface, not a generic "core" location |
| `iqoo/task_store.py` | `interfaces/api/task_store.py` | Same reasoning — this API's own storage component |
| `iqoo/events.py` | `interfaces/api/events.py` | The reconnect-safe SSE bus is specific to this HTTP interface |
| `iqoo/schemas.py` | `interfaces/api/schemas.py` | The request/response contract for this HTTP interface |
| `iqoo/server.py` | `interfaces/api/server.py` | The FastAPI app + routes for this HTTP interface |
| `iqoo/vision_adapter.py` | `multimodal/vision/adapter.py` | Interpreting a photo via a vision model is a generic SAM perception capability, not iQOO-specific |
| `iqoo/audio_adapter.py` | `multimodal/audio/adapter.py` | Transcribing audio (reusing `ears/stt.py`) is likewise generic |
| `iqoo/errors.py` | `multimodal/errors.py` | Perception exceptions belong with perception |
| `iqoo/media_validation.py` | `multimodal/media_validation.py` | Attachment validation belongs with perception |
| `client/*` | `interfaces/web/*` | The phone web client is a SAM Interface (channel), same category as Telegram |
| `ecosystem/telegram_bridge.py` | `interfaces/telegram/telegram_bridge.py` | Telegram is a SAM **Interface**, not device connectivity |
| `ecosystem/pair_new_device.py` | `interfaces/telegram/pair_new_device.py` | Same — it generates a pairing QR for the Telegram channel |
| `ecosystem/device_registry.py` | `connect/core/device_registry.py` | Device trust/pairing is **SAM Connect** infrastructure, independent of which interface uses it |

**Not moved, deliberately:** `ears/`, `mouth/`, `hands/`, `core/`, `agent/`,
`memory/`, `founder_mode/`, `skills/`. None of these have any iQOO coupling
and none benefit from being subdivided further for this migration — moving
stable code without cause just adds review risk.

## Compatibility strategy

`iqoo/` and `ecosystem/` are no longer implementation owners. Every module
in both packages is now a thin forwarding shim: it imports the real names
from the canonical location and re-exports them, so `import iqoo.gateway`,
`from ecosystem.device_registry import DeviceRegistry`, etc. keep working
unchanged for any code outside this repo (or inside it) that still
references the old path. There is exactly one implementation of each
component — the architecture boundary suite (below) checks this by object
identity (`iqoo.gateway.TaskGateway is interfaces.api.gateway.TaskGateway`),
not by inspection, so a future edit that accidentally forks the shim into a
second copy would fail the test immediately.

The two modules that are directly executable (`iqoo/server.py`,
`ecosystem/telegram_bridge.py`, plus `ecosystem/pair_new_device.py`) keep
their `if __name__ == "__main__":` block, but it only calls the canonical
`main()` — nothing is duplicated. `python -m iqoo.server` and
`python -m ecosystem.pair_new_device` were both run directly during this
phase (see Tests) to confirm the shim path boots the real implementation,
not just that the import succeeds.

New code should import from the canonical locations directly
(`interfaces.api.*`, `multimodal.*`, `interfaces.telegram.*`,
`connect.core.*`); the old paths exist for backward compatibility only.

## iQOO bridge status

`connect/bridges/vivo_iqoo/` remains documentation-only. The Phase 3A.5
audit reconfirmed there is no real vivo/iQOO vendor SDK, Office Kit API
call, or Bluetooth/LAN transport implementation anywhere in this codebase —
so nothing was fabricated to fill that directory. It holds a status
`README.md` and nothing else; the architecture boundary suite asserts this
directly (zero `.py` files under that path). Building a real bridge is
future work (Phase 3B+ territory, out of scope here).

## Ecosystem migration

`ecosystem/` is being phased out as an implementation-ownership layer the
same way `iqoo/` is. `ecosystem/__init__.py` now carries a docstring
explaining the compatibility role (it previously had none). The on-disk
data directory is still literally named `ecosystem` — see Persistent-data
compatibility below; moving Python modules does not rename a user's
existing SQLite file.

## API compatibility

No HTTP route was renamed. `/api/iqoo/tasks`, `/api/iqoo/tasks/{task_id}`,
`/api/iqoo/tasks/{task_id}/cancel`, `/api/iqoo/tasks/{task_id}/retry`,
`/api/iqoo/tasks/{task_id}/events`, `/api/iqoo/health`, and
`/api/iqoo/demo/reset` are unchanged — only the Python module implementing
them moved. The web client (`interfaces/web/`) needed no changes, since it
talks to those routes over HTTP and has no Python import path of its own.
Verified directly: `interfaces.api.server.app.routes` still contains every
route above (see the new architecture boundary suite), and the shim-booted
server (`python -m iqoo.server`) answered a real `GET /api/iqoo/health`
request during this phase's verification.

## Persistent-data compatibility

Nothing under `~/.sam_data/` moved or was renamed:

- Task store: still `~/.sam_data/iqoo/tasks.db` (`interfaces/api/task_store.py`
  keeps the directory name `iqoo` for exactly this reason — it's a data
  path, not a code path).
- Device registry: still `~/.sam_data/ecosystem/devices.db`, same reasoning.

Memory and Founder Mode schemas were not touched.

## Tests

**Fixed (were broken by the move, now passing):** the pre-existing
`iqoo`/Telegram test files patch/import specific symbols by dotted path,
and several of those paths pointed at the old (now-shim) modules, which no
longer hold those symbols:

- `tests/test_iqoo_phase1_offline.py`, `test_iqoo_phase2_offline.py`,
  `test_iqoo_phase3a_offline.py` — `mock.patch("iqoo.gateway.VisionAdapter")`
  / `AudioAdapter` and `patch("iqoo.vision_adapter.requests.post")` no
  longer had anything to patch, because the shim modules don't import those
  names at module level (only the canonical modules do). Repointed to
  `interfaces.api.gateway.*` / `multimodal.vision.adapter.*`. Same for the
  plain imports (`from iqoo.gateway import TaskGateway` →
  `from interfaces.api.gateway import TaskGateway`, etc.).
- `tests/test_phase2_telegram_offline.py` — one check
  (`test_device_registry`'s "Expired token rejected") mutates
  `dr_module.PAIRING_TOKEN_TTL_MINUTES` to force an immediate expiry.
  `DeviceRegistry.create_pairing_token()` reads that name as a module
  global from wherever it's *defined* (`connect/core/device_registry.py`),
  not wherever it was imported. With the test importing
  `ecosystem.device_registry as dr_module`, the mutation landed on the
  shim's own re-exported copy and silently had no effect — the check still
  ran, it just tested nothing. Confirmed empirically (ran the suite before
  fixing: 19/20, with exactly that check failing) and fixed by importing
  `connect.core.device_registry as dr_module` instead.
- A handful of comments that pointed at a specific old file+line for
  further reading (e.g. "see iqoo/gateway.py's comment at that catch
  site") were repointed to the file's new location. Comments that
  narrate *what a past phase did* (in `docs/iqoo/*.md`,
  `docs/PHASE_2_TELEGRAM_BRIDGE.md`) were left alone — they're accurate
  descriptions of history, not stale pointers.

**Added:** `tests/test_architecture_boundaries_offline.py` — a new offline
suite (106 checks) that verifies the invariants this document claims,
in code:
canonical implementations exist; every shim symbol is the *same object* as
its canonical counterpart (not a copy); the executable shims'
`__main__` blocks only ever call `main()`; `connect/bridges/vivo_iqoo/`
has zero `.py` files; SAM Core (`core/`, `agent/`, `memory/`,
`founder_mode/`, `skills/`, `multimodal/`) has zero imports of
`iqoo`/`ecosystem`/any vendor bridge; the canonical `interfaces/`/
`connect/core/` layer never imports back into a shim; every old dotted
import path still resolves at runtime; and the HTTP routes + on-disk DB
paths listed above are unchanged.

**Full offline regression, run fresh (isolated `HOME` per suite) after all
fixes above:**

| Suite | Result |
|---|---|
| `test_architecture_boundaries_offline.py` (new) | 106/106 |
| `test_iqoo_phase1_offline.py` | 56/56 |
| `test_iqoo_phase2_offline.py` | 51/51 |
| `test_iqoo_phase3a_offline.py` | 44/44 |
| `test_phase2_telegram_offline.py` | 20/20 |
| `test_phase1_offline.py` | 14/14 |
| `test_phase15_offline.py` | 22/22 |
| `test_founder_mode_offline.py` | 10/10 |
| `test_persistent_memory_offline.py` | 3/3 |
| `test_licensing_offline.py` | 14/14 |
| `test_feature_tier_offline.py` | 9/9 |
| `test_latency_fixes_offline.py` | 16/16 |
| `test_browser_thread_affinity_offline.py` | 10/10 |
| `test_concurrency_and_vision_fixes_offline.py` | 7/7 |
| `test_task_request_and_stagnation_offline.py` | 16/16 |
| **Total** | **398/398** |

`test_founder_mode_live.py` was not run — it requires a real running Ollama
instance with a pulled model, which this offline verification pass doesn't
have; that's unrelated to this migration and unaffected by it.

`python -m compileall .` — clean, zero errors, whole repository.

Import validation — every top-level package (`iqoo`, `ecosystem`,
`interfaces`, `interfaces.api`, `interfaces.telegram`, `connect`,
`connect.core`, `multimodal`, `multimodal.vision`, `multimodal.audio`,
`core`, `agent`, `memory`, `founder_mode`, `skills`, `ears`, `mouth`,
`hands`) imports cleanly in a fresh process, as do `main.py` and
`sam_cli.py`.

Circular-import checks — re-ran the same imports in reversed order
(canonical before shim), and in a fresh process that touches *only* the
shim paths and never the canonical ones directly. Both orderings import
cleanly; no circular dependency between the shim and canonical layers.

`python -m iqoo.server` was started for real (isolated `HOME`, 6s timeout):
it booted the actual FastAPI app, initialized Identity/Founder
Mode/task-store DBs, bound `0.0.0.0:8420`, and answered a real
`GET /api/iqoo/health` with a normal `"degraded"` response (expected —
no Ollama/Whisper backend is available in this offline sandbox, so
`brain_reachable`/`whisper_available` are correctly reported `false`).
`python -m ecosystem.pair_new_device` was also started for real: it reached
the canonical implementation's own config validation and exited with its
normal, correct error (`telegram_bot_username isn't set`) — proving the
shim delegates properly, not that anything is broken.

## Remaining limitations / deferred

- `docs/iqoo/PROGRESS.md` and `docs/iqoo/TEST_PLAN.md` were intentionally
  **not** edited — they're phase-by-phase historical logs, and this
  document is additive to them rather than a replacement. A future pass
  can append a Phase 3A.5 entry to each if that running-log format is
  still wanted.
- `connect/bridges/`, `connect/transports/`, `connect/direct/`,
  `connect/services/` beyond `bridges/vivo_iqoo/` do not exist yet —
  correctly deferred; creating empty placeholders for them would be
  speculative scaffolding with no current implementation behind it.
- `runtime/` and `installer/` (from the long-term target tree) do not
  exist yet — out of scope for this phase, per its own instructions.
- No git operations were performed as part of this phase (no add, commit,
  reset, or push) — the working tree's staged/unstaged/untracked state is
  exactly as it was, plus this phase's file edits, for review before a
  manual commit.
