# Brain / model selection and desktop correction

Scope: the iQOO x Reskilll Hackathon 2026 track. Two product/architecture
flags, resolved on top of the Phase 1 consolidation baseline:

1. Local Brain/model selection wasn't exposed or functional.
2. The desktop app didn't represent SAM's role (SAM is a local-first
   autonomous computer agent; the browser is one Hands capability; iQOO is one
   workspace).

Nothing here touches Phase 1 Hands/Vision reliability, retry/stagnation
architecture, the Sovereign/SIH stack, memory, licensing or installers.

---

## 1. Audit — what existed

### Brain / model selection

| Question | Finding |
|---|---|
| Default model | `Settings.primary_model = "qwen2.5:14b"`, `fallback_model = "qwen2.5:7b"` (`config/settings.py`). Unless `model_explicitly_set`, `_select_model()` overrides the primary by RAM tier (>=32 GB: 32b, >=16 GB: 14b, else 7b). |
| Source of truth | `config/settings.py`, overridable by `~/.sam_data/settings.yaml` (else `config/settings.yaml`). The loader reads one of those two files, never both. |
| Hardcoded? | Only the dataclass defaults and the RAM tiers. `core/brain.py`'s header docstring said "Qwen 2.5 14B" (corrected). |
| Who reads the model | `Brain._ensure_model()` reads `settings.primary_model` then `fallback_model` **on every request**. Planner, reflection, Founder Mode classifier and memory extraction also read `primary_model` per call, unless pinned by `planner_model` / `reflection_model` / `founder_mode_classifier_model`. Only Brain has fallback logic. |
| Ollama queried for installed models? | Only privately, inside `Brain._check_ollama()` / `_ensure_model()` (exact-name match on `/api/tags`). No public discovery. |
| API exposure | The gateway (`interfaces/api/server.py`) exposed nothing about models. `api/app.py` (VEDA/SIH stack, separate process, its own Brain) has a read-only `GET /api/model`; the desktop app never called it. |
| Desktop exposure | `/models` was a DEMO page with a hardcoded list; Settings' primary/fallback fields were DEMO text inputs; Command Center's Model card was PLANNED. |
| Can the user change the Brain? | No. Not in the desktop app, not in the CLI. `main.py` printed "change anytime via ... a model-select command" but that command didn't exist. |
| Would a change reach the runtime? | Yes, if `Settings.primary_model` were mutated on the shared object: every consumer above reads it per call. That is why Brain did not need rewriting. |
| Persistence | `model_explicitly_set` and the yaml loader existed; nothing in production ever wrote them (`Settings.save()` had no production caller). |
| Existing implementation, disconnected | `tests/test_model_selection_offline.py` is a 46-check spec (M6.2) for `Brain.list_installed_models()`, a first-run model choice and a runtime `model X` command. None of it was implemented; the file crashed on its first test at baseline. `docs/PHASE_1_CONSOLIDATION_REGRESSION_REPAIR.md` classifies it as a pre-existing failure, and `main.py`'s first-run docstring deferred model selection as out of scope for that pass. |

Terms, used precisely in code and UI:

- **installed** — present in Ollama (`/api/tags`)
- **discoverable** — installed and listed by SAM with metadata (`/api/show`)
- **selected** — `Settings.primary_model`
- **fallback** — `Settings.fallback_model`
- **active** — what Brain would use for the next request (selected if installed, else fallback if installed, else nothing)
- **compatible** — never claimed; see below

### What "compatible" would even mean for SAM's Brain

Brain calls `/api/chat` with `format: "json"` and expects
`{"text", "action", "action_payload"}` back, driven by a long system prompt.

| Factor | Required? |
|---|---|
| Chat capability | Yes — an embedding-only model can't work |
| Structured output / JSON reliability | Yes, in practice. On invalid JSON Brain degrades to plain text, and every action is silently lost |
| Ollama native tool calling | **No.** Brain sends no `tools` field |
| Vision | **No.** Screen reading uses the separate `vision_model` |
| Context length | `num_ctx = model_context_length` (8192). A model with a smaller limit is flagged |
| Prompt behavior | The prompt was developed against Qwen 2.5; nothing verifies another model follows it |
| Reasoning ("thinking") models | Risk: thinking tokens count against `max_tokens` (1024), and JSON mode with reasoning output is unverified |

None of that can be verified from Ollama metadata, so compatibility is
**conservative and has no "compatible" value**: `incompatible` (provably
unusable: SAM's configured embedding model, or Ollama reports no `completion`
capability) or `unknown` (everything else). Extra notes surface real metadata:
thinking capability, context below `num_ctx`, SAM's configured vision model.

### Desktop / product structure

| Finding | Detail |
|---|---|
| What the "desktop app" is | A Vite SPA served in a browser tab (`interfaces/desktop/`). No native shell exists. |
| Browser-specific UI | There was none. The browser feel came from being a browser SPA, from iQOO being the only live area, and from the demo placeholders. |
| Framing problem | The only live backend is the task gateway under `/api/iqoo/`, so general task execution was presented as "the iQOO gateway". iQOO was a top-level nav group. |
| Placeholders | Chat (DEMO), Tasks (PLANNED stub), Models (DEMO), Settings model fields (DEMO), Command Center Model card (PLANNED). |
| Missing | General task surface (Tasks), Brain control, any Hands/capabilities view. |
| Disconnected backend | `TaskStore.list_tasks()` exists but no endpoint exposes it; the desktop can only show tasks submitted from this app. |
| A real chat path? | Yes: text tasks go through the real Brain and ReAct loop, and a direct answer comes back as the task result. It is single-turn (`Session.history` is empty for every gateway task), so Chat was connected honestly to it. |
| Duplicates | `client/` is a stale near-duplicate of `interfaces/web/`; `tests/test_architecture_boundaries_offline.py` (test I) expects it removed. Not touched here. |

---

## 2. What changed

### Runtime flow

```
Ollama /api/tags + /api/show
        |  core/model_manager.py: discovery, compatibility (read-only)
        v
GET /api/models  ------------>  Brain page / Command Center card
POST /api/models/select
        |  validate: reachable, installed, metadata readable, not provably unusable
        |  gateway: refuse while a task is running or queued (409)
        v
Settings.apply_model_choice()   sets primary_model + model_explicitly_set,
        |                       writes ~/.sam_data/settings.yaml atomically
        v
Settings.primary_model          THE source of truth (unchanged)
        v
Brain._ensure_model() / planner / reflection / classifier / memory
        read it on their next call: no restart, no second copy
```

### Files

Backend: `core/model_manager.py` (new), `core/brain.py` (+`list_installed_models`,
docstring), `config/settings.py` (+`apply_model_choice`), `interfaces/api/gateway.py`,
`interfaces/api/schemas.py`, `interfaces/api/server.py`, `main.py`.
Desktop: see `interfaces/desktop/README.md` (Brain, Tasks, Hands, Chat, nav,
Command Center, iQOO Workspace, Settings, `api/`, `services/brain.ts`, store).
Tests: `tests/test_brain_model_management_offline.py` (new).

### API

Served by the existing gateway, beside `/api/iqoo/*` rather than under it
(choosing the Brain is SAM Core, not the phone-task contract; the
`/api/<domain>` shape is the one PHASE5_PLAN §F proposed). The `/api/iqoo/*`
contract is unchanged.

| Route | Purpose |
|---|---|
| `GET /api/models` | Provider status, selected/fallback/active/last-used model, `busy`, pinned overrides, and every installed model with metadata and compatibility. Ollama being down is `status: "unavailable"`, not a 5xx. |
| `POST /api/models/select` `{model}` | Validate, switch, return fresh status. `409` a task is running/queued, `404` not installed, `422` provably unusable, `502` metadata unreadable, `503` Ollama unreachable, `500` save failed (nothing changed). |

Every response field is consumed by the desktop UI, and the Python schema,
the manager's output and `src/api/types.ts` are checked field-for-field by
`tests/test_brain_model_management_offline.py`.

### Behavior worth knowing

- **Names are normalised to Ollama's installed spelling** (`qwen3` becomes
  `qwen3:latest`). Brain matches names exactly, so storing the short form would
  silently fall back.
- **Switching is refused while a task runs or is queued.** The Ollama round
  trips happen outside the gateway's lock; the busy check and the settings
  write are repeated together under it, so a task can't start half-way through
  a switch.
- **Persistence is targeted, atomic and leak-free.** `Settings.save()` dumps
  every live field, including runtime-only state: the voice loop's `incognito`
  command flips `settings.incognito` in memory, and saving it would start every
  future session in incognito. `apply_model_choice` instead updates only the
  model keys in the file the loader would read (the user's yaml, else
  `config/settings.yaml`), then replaces the file atomically. If the write
  fails, the in-memory change is rolled back.
- **Fallback** is unchanged logic (Brain's) and is now visible: the status says
  when the selected model isn't installed and the fallback is in use.
- **Pinned subsystems** (`planner_model`, `reflection_model`,
  `founder_mode_classifier_model`) don't follow a switch; the status lists them.
- **CLI parity (M6.2):** `Brain.list_installed_models()`, a runtime
  `model` / `model <name>` command and the first-run model step now exist and
  share `Settings.apply_model_choice`. The CLI accepts an unverified choice when
  Ollama is unreachable (its spec); the desktop refuses. The command only
  claims a single-token name, so "model the data flow for a login page" still
  reaches the Brain. During first-run setup, `--name` counts as a scripted
  launch and skips the model prompts.

### Desktop

Navigation: Command Center, Chat, Tasks | Brain, Hands | iQOO Workspace |
Memory, Founder Mode, Skills | Diagnostics, Licensing | Settings.

- **Brain** (`/brain`, live): active model, provider, endpoint, status,
  selected/fallback, last model used, installed models with metadata,
  compatibility and a working selector. Replaces the demo `/models` page.
- **Tasks** (`/tasks`, live): general console with the lifecycle
  (understand, plan, execute, verify, result) derived only from phases the
  gateway emits (a stage a task never entered shows as skipped), live events,
  cancel, retry. No browser or iQOO framing.
- **Hands** (`/hands`): what SAM can do, read from the ReAct action table:
  desktop control, vision, browser, terminal, verification, phone-originated
  tasks, and Office Kit explicitly listed as not implemented. Static except
  the vision/Whisper rows, which come from gateway health.
- **Chat** (`/chat`, live): each message is submitted as a real task; SAM's reply
  is the outcome. States its limits on screen.
- **Command Center**: real Brain card instead of the PLANNED placeholder;
  copy no longer calls the general task path "the iQOO gateway".
- **iQOO Workspace**: unchanged behavior, scoped as the phone-to-PC workflow.
- **Settings**: the dead primary/fallback rows were removed in favor of a
  pointer to the live Brain page (one control, not two).

Deliberately not changed: browser automation, Playwright, all Hands code,
Phase 1 reliability code, the ReAct loop, `react_loop.py`, Memory / Founder
Mode / Skills / Diagnostics / Licensing demo screens, the design system, the
phone client (`interfaces/web/`), the VEDA stack (`api/`, `frontend/`), and
`client/`.

---

## 3. Limitations (explicit)

1. **Compatibility can't be verified.** Every chat-capable model is "unknown".
   A model may pass the checks and still fail SAM's JSON action format. A live
   probe (send a tiny JSON-protocol request and validate it) would be the next
   step; it wasn't added because it needs a real Ollama to validate.
2. **Reasoning models (for example Qwen 3) are unverified** and flagged. Their
   thinking tokens count against `max_tokens` (1024); Brain does not pass
   Ollama's `think` option. Not changed: Brain wasn't rewritten.
3. **The desktop switch applies to the gateway process only.** The gateway,
   the `main.py` voice/text session and the Telegram bridge are separate
   processes, each with its own `Settings`. The choice is persisted, so the
   others pick it up when they restart; until then they keep their model.
4. Ollama keeps the previous model loaded for its keep-alive window, so two
   large models can briefly be resident together.
5. The first change rewrites `~/.sam_data/settings.yaml` (YAML comments in it
   are not preserved).
6. Chat is single-turn with no streaming; Tasks lists this session's tasks
   only (the ledger has `list_tasks()`, no endpoint exposes it).
7. Hands availability isn't probed except vision/Whisper.
8. The desktop app is still a browser-tab SPA; a native shell is out of scope.
9. `/models` no longer exists (it was the demo page).
10. Pre-existing, untouched: `test_macos_screenshot_and_terminal_exit_offline`,
    the `client/` duplicate (arch test I), and three assertions in
    `test_model_selection_offline.py` that assume a 16-31 GB Mac's default
    (`qwen2.5:14b`); on other RAM tiers `Settings()`'s auto-selected default
    differs.

---

## 4. Tests

`tests/test_brain_model_management_offline.py` (fake Ollama, no network, no
personal installation): discovery parsing, empty list, Ollama unavailable (3
modes), active model (selected/fallback/neither), agreement with
`Brain._ensure_model()`, conservative compatibility, valid and invalid
selection, name normalisation, persistence (targeted, atomic, rollback),
runtime Brain and planner actually receiving the selected model, state
consistency, gateway busy/queued/race behavior, HTTP status mapping, the
schema/manager/TypeScript contract and that every field is consumed, and the
desktop product structure. The existing `tests/test_model_selection_offline.py`
(M6.2) now passes.

Run: `python -m pytest -q` (checks raise under pytest), or
`python3 tests/test_brain_model_management_offline.py` (isolates `HOME`).

---

## 5. Manual validation on the Mac

Prerequisites: Ollama running with at least two chat models pulled (for
example the default and one other) plus `nomic-embed-text`.

```bash
python -m pytest -q
python -m interfaces.api.server        # gateway on :8420
cd interfaces/desktop && npm install && npm run build && npm run dev
```

**A. Brain**

1. Open `/brain`. Status is Ready; every installed model is listed
   (including `nomic-embed-text`, marked Incompatible with a disabled button).
2. Active shows the expected model; the source line says "chosen by you" or
   "SAM's default".
3. Click "Use as Brain" on another chat model. The row moves to In use and a
   confirmation appears only after the server answers.
4. On `/tasks` submit "What is 15% of 3400?". Return to `/brain`: "Last used by
   SAM" is the new model. In a terminal, `ollama ps` shows it loaded.
5. Switch back; repeat step 4; it works again.
6. While a task is running, the buttons are disabled with an explanation; a
   direct `POST /api/models/select` returns 409.
7. Restart the gateway: the choice persists. `~/.sam_data/settings.yaml` has
   `primary_model` and `model_explicitly_set: true` and no `incognito` key.
8. Stop Ollama, refresh `/brain`: Unavailable with "Start it with: ollama serve".
9. `ollama rm` the selected model, refresh: Active shows the fallback, with the
   reason.

**B. General execution** (on `/tasks`; check the lifecycle strip and events)

- "Open Safari" (app launch; the result should say it was confirmed in the foreground)
- "Open Spotlight and search for Notes" (Spotlight interaction)
- "Click the ... in <an app window>" (desktop UI interaction)
- "Go to example.com and read the heading" (browser)
- "Take a screenshot" (screen capture; needs Screen Recording permission)
- A target that doesn't exist ("Open NonexistentApp123", "click the purple
  unicorn"): the task must end **failed** with a specific reason, never
  completed. SAM must not claim success because an executor returned a
  success string.

**C. Product surface**

- The sidebar reads SAM / Brain and Hands / Workspaces; the browser appears
  only as one card on `/hands`.
- `/chat` replies with real task outcomes and states it is single-turn.
- `/iqoo` still works: health, task submission, Demo reset. Phone client
  (`interfaces/web/`) still submits tasks to the same gateway.
- Command Center's Brain card matches `/brain`.
