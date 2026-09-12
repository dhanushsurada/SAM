# SAM Phase 5 — Frontend/UI/UX Plan

Grounded against the actual working tree (`SAM-iqoo-2026-working-tree-updated.zip`),
not the product doctrine alone. Where the two disagree, this document says so
explicitly rather than quietly picking one.

---

## A. Current frontend/backend capability map

**Three web-facing surfaces exist in this repo today — only one is in scope here.**

1. **`frontend/` — not SAM.** This is *VEDA — Sovereign Industrial AI Workbench*,
   built for a different hackathon (Smart India Hackathon, problem statement
   SIH26117, branch `sih26117`, merged into this working tree). Zero-build CDN
   React, a neutral paper/ink palette, a document-ingestion/evidence/sovereignty
   domain. It is excluded entirely from this plan: not a base, not a style
   reference, not touched.
2. **`interfaces/web/` — the real, narrow SAM iQOO phone client.** Vanilla
   HTML/CSS/JS, zero-build by deliberate choice (its own README: "adding a JS
   build toolchain just for this branch would be scope creep for a 30-hour
   competition window"). Covers the task composer, camera/voice capture, and
   live execution progress. Explicitly untested on real hardware. Left as-is —
   real, working, hackathon-critical, out of scope to rebuild.
3. **Nothing else.** `docs/ROADMAP_STATUS.md` (July 2026) states it plainly:
   *"There is no GUI... entire product is CLI-only today."* A full route grep
   across the repo confirms this is still true.

**Every HTTP route that exists, repo-wide:**

| Route | File | Status |
|---|---|---|
| `POST/GET /api/iqoo/tasks`, `/{id}`, `/{id}/cancel`, `/{id}/retry`, `/{id}/events` (SSE), `/health`, `/demo/reset` | `interfaces/api/server.py` | **Real, working** — this is SAM's actual API |
| `/api/status`, `/api/model`, `/api/documents`, `/api/knowledge/search`, `/api/tasks*`, `/api/sovereignty/{id}` | `api/app.py` | Real, but this is VEDA's API — different product |

Everything the product doctrine describes beyond that — Brain, Memory, Founder
Mode, Skills, Runtime lifecycle, Licensing — exists only as **Python classes
called in-process** by `main.py` (the voice loop) and `sam_cli.py` (the CLI).
No HTTP layer, no exceptions:

- `memory/store.py` → `MemoryStore.save_episode / get_recent_episodes /
  save_semantic / search_semantic / extract_and_save`. SQLite + ChromaDB.
  **No delete/reset method exists even internally** — a "clear memory" button
  has nothing to call yet, at any layer.
- `founder_mode/manager.py` → `FounderModeManager.capture_decision /
  capture_rejection / update_taste / get_context / list_llm_captures /
  confirm_capture / reject_capture / export`.
- `skills/compiler.py` → `SkillCompiler.record_successful_task /
  find_compiled_skill / list_skills`. **No manual "execute" method** — skills
  are matched automatically during task execution, never invoked directly, so
  a UI "run skill" button also has nothing to call yet.
- `runtime/lifecycle/manager.py` → `SAMRuntime.start/stop/restart`,
  `status_all()`, `health_all()`, per named process.
- `licensing/license_manager.py` → `LicenseManager.install_license / check`.
- `core/brain.py` + `agent/react_loop.py` — the actual reasoning/execution
  engine. Reached today only via the voice loop or the iQOO gateway's
  adapters, never directly over HTTP.

`config/settings.py` has concrete, real fields for nearly every Settings
category the brief wants (model/fallback, wake word, Whisper, TTS, memory
paths, Founder Mode, Telegram, API host/port, licensing, skills paths) — a
genuinely useful shape for the Settings screen — but nothing reads or writes
it over HTTP today.

**The single biggest gap:** there is no concept of "chat" as an HTTP
request/response today. `main.py` calls `Brain.process(session)` in-process,
inside a live voice loop — not as a server answering requests. Every other
gap in this map is "the method exists, no endpoint wraps it yet." Chat is
different: it's a live long-running process talking to itself, with nothing
resembling a stateless request cycle to wrap. This is the deepest hole to
design the UI's API boundary around.

**Bottom line:** the iQOO task flow is real, end to end. Everything else this
brief asks for is a UI waiting for a backend that doesn't exist yet, in whole
or in part.

---

## B. Proposed frontend architecture

**Stack: React 19 + TypeScript + Vite + Tailwind CSS.**

This matches the original spec. One constraint changes *how* it gets built,
not *what* gets built: this sandbox has no network access, so `npm create
vite`, `npm install`, and an actual Vite dev server aren't available to me —
the same wall this repo has already hit twice (VEDA's frontend, and
`interfaces/web/`'s own build-tooling notes). What *is* available locally,
no network required: Node 22, TypeScript 6.0.3, React 19 / ReactDOM 19 — all
pre-installed. No bundler, no `@types/react`.

So the approach is: write real `.tsx`/`.ts` source, and verify it with local
`tsc` against a small hand-written type shim covering the React APIs actually
used (`src/types/react-shim.d.ts`, clearly marked dev-only). Tested this
end-to-end before committing to it — it genuinely catches type errors (e.g.
a missing required prop), not just syntax. That's real but partial
verification, not equivalent to `@types/react` or an actual Vite build. The
`package.json` / `vite.config.ts` / `tsconfig.json` shipped here are the real,
standard ones — the first `npm install && npm run dev` you run gets you onto
the genuine toolchain, and the shim becomes dead weight you can delete once
real `@types/react` is installed (a comment in the file says so).

Not depending on shadcn/ui or Radix as actual packages, for the same
reason — can't verify an install I can't run. Instead: hand-written,
accessible primitives (Button, Badge, Dialog, Tabs...) using native HTML +
ARIA + Tailwind, in the same composable shape shadcn uses. Swapping in real
shadcn later is mechanical, not a rewrite, if you ever want it.

---

## C. Proposed directory structure

`frontend/` is taken (VEDA). The new product UI lives at
**`interfaces/desktop/`** — extends the existing `interfaces/{api,telegram,web}`
convention, and the name draws a clear line against `interfaces/web/`'s narrow
phone-client scope, matching the brief's "desktop-first, mobile/tablet
adapted" direction.

```
interfaces/desktop/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  tailwind.config.ts
  README.md
  src/
    main.tsx
    App.tsx
    app/                 routing, providers, theme, app shell wiring
    components/          design-system primitives (Button, Card, Badge...)
    layouts/             AppShell, Sidebar, TopBar, ContextPanel
    features/
      command-center/
      chat/
      tasks/
      iqoo/
      memory/
      founder-mode/
      skills/
      models/
      diagnostics/
      settings/
      licensing/
    services/            one interface per domain; real + demo implementations
    api/                 typed HTTP client, request/response types
    hooks/
    stores/
    types/
    styles/              design tokens (CSS variables), globals
    assets/
```

This matches the brief almost exactly — only the top-level folder name
changed (`frontend/` → `interfaces/desktop/`), for the collision reason above.
Deviation noted per the brief's own instruction to explain deviations.

---

## D. Page/screen inventory

| # | Screen | Backend today | This build |
|---|---|---|---|
| 1 | Command Center (Home) | Partial (iQOO health/recent tasks real; rest isn't) | Real iQOO summary + clearly labeled demo sections |
| 2 | AI Interaction / Chat | None | Full UI + typed API boundary; demo responses |
| 3 | Task Execution / Agent Console | Real for iQOO-originated tasks | Real status/cancel/retry/SSE; demo framing for non-iQOO sources |
| 4 | iQOO / Phone Gateway workspace | Real | Real — the one screen built entirely on live data |
| 5 | Memory | None | Demo, typed contract documented (§F) |
| 6 | Founder Mode | None | Demo, typed contract documented (§F) |
| 7 | Skills | None | Demo, typed contract documented (§F) |
| 8 | Models / Brain | None (config only) | Demo, typed contract documented (§F) |
| 9 | System / Diagnostics | None (health module exists, unwired) | Demo, typed contract documented (§F) |
| 10 | Settings | None (config fields exist, unwired) | Demo read/write UI over real field shapes |
| 11 | Licensing | None (`LicenseManager.check()` exists, unwired) | Demo, typed contract documented (§F) |

Every demo screen gets a visible mode indicator (see design system, §E) —
never silently indistinguishable from live data, per the brief's own rule.

---

## E. Component / design-system inventory

**Design-system brainstorm** (frontend-design process: plan → check against
brief for genericness → build):

- *Subject:* not a chatbot, not an admin dashboard — a legible instrument
  panel for one autonomous local process. The job is making an otherwise
  invisible, always-on agent's state trustworthy at a glance.
- **Color** (base palette, 6 named values):
  `--sam-void #0C0E12` (base bg), `--sam-surface #15181D` (panels),
  `--sam-line #262B31` (borders), `--sam-ink #EDEFF2` (primary text),
  `--sam-mute #8A9099` (secondary text), `--sam-ember #F2761E` (accent).
  Ember is deliberately *not* Claude's `#D97757` — more saturated, more true-
  orange, less pink — distinct on sight, not a reuse. Status colors are
  functional, not decorative: verified/success green, warn amber-gold
  (visually distinct from ember so "brand" and "caution" never collide),
  failed red, unverified a desaturated blue-grey (reads as *unknown*, not
  *bad* — matters given how much of this product is honestly unverified).
  Full light theme included, not just dark (brief asks for both).
- **Type:** IBM Plex Sans (UI/prose) + IBM Plex Mono (status codes, model
  names, ports, timestamps, PASS/WARN/FAIL strings). Chosen over the far more
  common Inter-as-default specifically because SAM's UI actually needs to
  render technical readouts constantly — the mono pairing is earned by the
  content, not decorative. Same family for both, so they cohere.
- **Layout:** slim sidebar (identity, nav, one compact live status pulse) +
  main workspace + a *contextual* right panel that appears only where a
  screen needs it (task detail, activity), rather than a permanently reserved
  third column — avoids the generic fixed-3-column SaaS-dashboard read while
  keeping the structure the brief asked for.
- **Principles:** one accent, spent deliberately; hierarchy through spacing
  and type weight before color; every card's elevation and radius says
  something about its role rather than being uniform; motion answers actions
  (task state changes, panel open/close) rather than decorating page load.

**Primitives:** Button, IconButton, Input, Textarea, Select, Switch,
Badge/StatusPill (carries the IDLE/LISTENING/THINKING/EXECUTING/WAITING/
NEEDS_CONFIRMATION/SUCCESS/FAILED/CANCELLED/UNAVAILABLE/UNVERIFIED semantics
from the brief as one shared component), Card, Panel, Tabs, Dialog, Drawer,
Tooltip, DropdownMenu, Toast, Skeleton, EmptyState, ErrorState, ModeBadge
(the DEMO/LIVE indicator, applied per-screen and per-data-block).

**Composite:** CommandBar, TaskCard, TimelineItem, MetricCard, NavItem,
ChatBubble, ExecutionStep, ConfirmDialog (for destructive actions, per the
brief's requirement).

Built this turn: design tokens (light + dark), global styles, and two
grounded primitives (Button, StatusPill) as concrete proof of the pattern —
see §H for what's next.

---

## F. Real-vs-demo integration boundary — endpoints required

Format: endpoint · wraps · purpose · priority. Grounded in the actual method
signatures found in the repo, not invented shapes.

**Memory**
- `GET /api/memory/episodes?limit=&retention_days=` → `MemoryStore.get_recent_episodes` · recent-memory list · P1
- `GET /api/memory/search?q=&top_k=&retention_days=` → `MemoryStore.search_semantic` · semantic search · P1
- Delete/reset action → **no backing method exists anywhere yet**, internal or HTTP. Needs a new `MemoryStore` method before it needs an endpoint. · P2

**Founder Mode**
- `GET /api/founder-mode/context` → `get_context()` · P1
- `GET /api/founder-mode/decisions?limit=&min_confidence=` → `_get_recent_decisions` (currently private — needs a public wrapper) · P1
- `GET /api/founder-mode/taste?min_confidence=` → `_get_taste_profile` · P1
- `GET /api/founder-mode/pending-captures` → `list_llm_captures` · P2
- `POST /api/founder-mode/captures/{table}/{id}/confirm|reject` → `confirm_capture`/`reject_capture` · P2

**Skills**
- `GET /api/skills` → `list_skills()` · P2
- "Execute skill" as a UI action → **no manual-invoke method exists**; skills are matched automatically inside task execution, never called directly. Needs new capability, not just a new route. · P3

**iQOO task history**
- `GET /api/iqoo/tasks` (list) → **doesn't exist** — only get-by-id
  (`GET /api/iqoo/tasks/{id}`) does, confirmed reading `interfaces/api/server.py`
  directly. The desktop iQOO workspace's task list is therefore
  session-scoped only (tasks created since the page loaded, held in React
  state) — refreshing the page loses it. Needed for genuine persistent
  history. · P2

**Runtime**
- `GET /api/runtime/status` → `SAMRuntime.status_all()` · P1
- `GET /api/runtime/health` → `SAMRuntime.health_all()` · P1
- `POST /api/runtime/{name}/start|stop|restart` → `SAMRuntime.start/stop/restart` · P2

**Licensing**
- `GET /api/license` → `LicenseManager.check()` · P2
- `POST /api/license/install` → `install_license()` · P2

**Models / Brain**
- `GET /api/model/status` → needs new code; `Brain._check_ollama()` /
  `_ensure_model()` are private and nothing currently surfaces Ollama
  availability or the active model outside the process itself. · P2

**Settings**
- `GET /api/settings` / `PUT /api/settings` → wraps `Settings` (read
  current values / call `.save()`). Doesn't exist — `Settings.save()`
  writes `~/.sam_data/settings.yaml` directly, with no HTTP path to reach
  it from a browser. Needed before the Settings page's edits can persist
  at all, not just before they're "real" — right now there's no seam even
  to fake convincingly beyond local state. · P2

**Chat**
- `POST /api/chat` (or a session/streaming variant) → nothing today calls
  `Brain.process(session)` from outside the voice loop. This is a new
  capability, not a wrapper — see §A. · P1 if a live chat demo matters more
  than the other gaps; otherwise the honest lowest priority, since it's the
  most work for the least reuse of what already exists.

---

## G. Migration / cleanup plan

- Nothing migrates *from* `frontend/` — it belongs to VEDA, untouched, not
  read for reuse beyond the technical pattern-check already done.
- `interfaces/web/` stays exactly as-is. Not merged into `interfaces/desktop/`,
  not rebuilt — it's real, working, and hackathon-critical. `interfaces/desktop/`
  calls the *same* iQOO gateway (`interfaces/api/server.py`), just from a
  fuller product shell.
- No changes to `core/`, `agent/`, `memory/`, `runtime/`, `licensing/`, or the
  iQOO backend — confirmed against §33 of the original brief.
- One suggestion, not applied without confirmation: once the endpoints in §F
  exist, `interfaces/web/` could be reframed as the phone-optimized subset of
  `interfaces/desktop/` rather than a separate codebase. Future consolidation,
  not now.

---

## H. Implementation order

1. ✅ **Design tokens + primitives** — done. Tokens (light + dark), globals,
   `Button`, `StatusPill`.
2. ✅ **App shell** — done. `AppShell`/`Sidebar`/`TopBar`, routing via
   `react-router-dom` (`createBrowserRouter`), light/dark toggle
   (persisted, respects OS preference on first load), responsive (mobile
   gets a real slide-in drawer, not a shrunk desktop layout). All 11 routes
   exist and render — each currently through the shared `FeatureStubPage`,
   honestly labeled `PLANNED` with the step that builds its real version, so
   the nav is fully walkable today without pretending anything beyond the
   shell is finished. Added `ModeBadge` (planned/demo/live) and `EmptyState`
   to the component inventory — needed earlier than expected, once actual
   stub screens existed to label. A live system-status pulse was planned for
   the sidebar in §E but deliberately left out until step 3 gives it real
   data to show. Reference: `/_dev/design-system` route (not in nav) — a
   living style guide, not a product screen.
3. ✅ **Typed API client + service layer** — done, built alongside step 4
   below since iQOO needed both to mean anything. `src/api/` (wire types +
   HTTP/SSE client) and `src/services/iqoo.ts` (the domain interface every
   other domain's future demo implementation will also implement).
4. ✅ **iQOO workspace + Tasks** — done. `src/api/types.ts` and
   `src/api/client.ts` mirror `interfaces/api/schemas.py` field-for-field
   (checked directly against the file, not inferred). Real task
   create/cancel/retry, live SSE via the browser's native `EventSource`
   (server.py's `id:`-framed events are built specifically for this —
   no hand-rolled reconnect logic needed), health polling, demo reset.
   Image attachments validated client-side against the exact limits in
   `multimodal/media_validation.py` (8 MB, jpeg/png/webp) so a rejected
   upload never even reaches the network. Voice input is a visibly
   disabled control, not a half-built one — out of scope for this pass.
   `/tasks` still points at the shared stub: the backend has exactly one
   task source right now (iQOO), so a separate "Tasks" concept has nothing
   to unify yet — its stub copy explains this and points at `/iqoo`.

   Two real bugs caught by building this for real instead of mocking it:
   `EventSource`'s default behavior is to auto-reconnect after *any*
   stream close, including the server's own clean close on a terminal
   event — left alone, that reopens the connection every few seconds
   forever on a finished task, fixed by closing client-side on seeing a
   terminal phase. And `GET /api/iqoo/tasks` (list) doesn't exist at all
   (added to §F) — only get-by-id does, which is why the task list here is
   session-scoped rather than persistent.

   Known gap, not hidden: destructive-action confirmation
   (`handleDemoReset`) uses `window.confirm` as a functional stand-in — the
   styled, accessible `ConfirmDialog` primitive from §E isn't built yet.
4. iQOO workspace (real data) + Task Execution / Agent Console around it.
5. ✅ **Command Center (home)** — done. Required lifting task-session state
   (sessionTasks, selected task, health, all the submit/cancel/retry
   handlers) out of `IqooPage` and into `src/stores/taskSession.tsx` first —
   Command Center's quick input and `/iqoo`'s full workspace are two views
   onto the *same* live session now, not two independent copies that would
   silently diverge (a task sent from Home wouldn't appear at `/iqoo`
   otherwise, since React Router unmounts the outgoing route on
   navigation). `IqooPage` itself is now pure layout, no state of its own.
   Command Center's primary action — the quick task input — is genuinely
   real, not a mockup: it's the same `submitTask` hitting the same gateway.
   Model status is the one honestly-`planned` card on this screen.
6. ✅ **Chat (demo)** — done. Kept deliberately separate from `src/api/`:
   that folder mirrors *real* backend contracts, and there's nothing real
   to mirror here (confirmed in §A — chat isn't an unwired endpoint, it's a
   capability that doesn't exist outside the voice loop at all). So the
   proposed request/response shape lives in `src/features/chat/types.ts`
   instead, visibly speculative rather than implying verification it
   doesn't have.

   This screen carries the brief's "never present a fake operation as
   real" rule more heavily than any other: chat replies are exactly the
   kind of content that could pass for genuine reasoning if the only
   demo-marker were a corner badge. So every single reply says in its own
   text that it's a placeholder, on top of the page-level `ModeBadge` and a
   persistent banner — three layers, not one, specifically because the
   content itself is more convincing than a health check or a status pill
   would be.
7. ✅ **Memory, Founder Mode, Skills, Models, Diagnostics, Licensing** —
   done, all demo, each against the typed contracts already documented in
   §F. Lighter-weight than steps 4–6 by design — these are read-mostly
   informational screens, not live interactive ones, so the investment
   matches that: `src/components/PageHeader.tsx` extracted after the
   header pattern repeated a third time, one small `types.ts` +
   demo-data pair per domain.

   Specific honesty calls, not defaults: Memory's search box runs a real
   (if trivial) filter over the demo set rather than being decorative, but
   its "Clear" button is disabled with an explanation, since
   `MemoryStore` has no delete method to even pretend to call. Skills has
   no action buttons at all — confirmed again that no manual-invoke
   capability exists, so a page that let you "run" a skill would be
   fabricating a feature, not just fabricating data. Founder Mode's
   confirm/reject buttons do mutate local state (removing the item) —
   that's a real interaction pattern for a capability
   (`confirm_capture`/`reject_capture`) that genuinely exists, just not
   over HTTP, so simulating its effect is honest; Models and Diagnostics
   are pure display, matching what those screens would show even with a
   real endpoint.
8. ✅ **Settings** — done. Every field, default, and grouping in
   `src/features/settings/types.ts` is transcribed directly from
   `config/settings.py` (read in full again for this, not from memory of
   the earlier pass) — nothing invented, including the exact defaults
   (e.g. `primary_model: "qwen2.5:14b"`, `api_port: 8420`). Path-derived
   fields (`chroma_path`, `log_path`, etc.) render read-only rather than
   editable — they're derived from `SAM_DATA_DIR`, not something a
   settings UI should invite hand-editing. Two sections carry a note
   pulled from the source file's own comments: automation safety
   (`allow_risky_terminal_commands`, off by default — refuses rm/mv/sudo/
   kill rather than running them silently) and Telegram (an internet-relay
   bridge, explicitly *not* local, which is the one real exception to
   SAM's local-first network doctrine if enabled). Edits are local-state
   only, with that said plainly in the page description — `Settings.save()`
   writes a YAML file directly; nothing here can reach that without a new
   endpoint.
9. ✅ **Onboarding** — done, as a standalone route (`/onboarding`) outside
   `AppShell` entirely — no sidebar/topbar chrome, matching a first-run
   wizard rather than a page within the product. No auto-redirect into it:
   that needs a persisted "has onboarded" flag, and getting that wrong
   (looping, trapping a returning user) seemed worse than just leaving it
   reachable from a small link in Sidebar for now.

   The brief's own warning here — "do not replace the actual installer
   with frontend screens that do nothing" — shaped this more than any
   other single line in the whole document. A browser tab cannot install
   an Ollama model, cannot grant itself macOS Accessibility/Screen
   Recording permissions, and cannot touch SAM's native wake-word process
   at all (that's a separate OS-level process, not something this
   browser-based app talks to or represents). So: System Check is real
   (reuses the shared `useTaskSession()` health data, the same live
   gateway check as everywhere else) with no gating on it passing — you
   can set up the rest first and come back. Model & Voice and Permissions
   are explicitly informational, not interactive checklists that would
   just be theater — copyable `ollama pull` commands and the exact System
   Settings paths, not fake progress bars. Configuration doesn't duplicate
   the Settings page, it links to it.
10. ✅ **Responsive / accessibility / motion pass** — done, as a code-level
    audit and fix pass across steps 1–9, not a from-scratch build. Honest
    about its own limits below — this was reading the code with a phone
    viewport and a screen reader in mind, not running either.

    Two contrast fixes, computed against the actual WCAG formula rather
    than eyeballed (token values and math are in `tokens.css`'s comments):
    ember used as text/link/icon color directly against the page
    background computed to ~2.7:1 on the light theme's near-white
    surfaces — well under the 4.5:1 AA floor — while the *same* value
    works fine as a button fill (with `--sam-ember-ink` text on top,
    unaffected either way). One value couldn't serve both without failing
    contrast in one direction, so it split into two tokens:
    `--sam-ember` (fills, unchanged) and `--sam-ember-text` (text/icons/
    links, deepened to ~176/78/10 for light mode, computes to ~5.1:1).
    Separately, `--sam-unverified` in dark mode computed to ~4.0:1 against
    void — also under AA for the small text it renders as (task ids,
    timestamps) — lightened to ~148/154/166, now ~6.8:1.

    Structural fixes: two icon-only controls had no accessible name
    (`ChatComposer`'s send button, `TaskComposer`'s image-attach label) —
    both fixed. The mobile nav drawer closed on backdrop click but had no
    keyboard equivalent — added Escape-to-close. Added a skip-to-main-
    content link, since every page's content sat behind the full sidebar
    nav in tab order otherwise. `SettingsPage`'s field rows (label beside
    a fixed-width input) get tight against its longer labels below `sm` —
    changed to stack vertically there instead of side-by-side.

    **What this pass did *not* do**, stated rather than left implicit:
    no real browser or screen-reader testing (not possible in this
    sandbox) — this is a code-level review. Contrast was computed for the
    specific combinations that looked highest-risk (accent/status colors
    used as small text), not exhaustively for every color pairing in the
    app, and border contrast (the separate 3:1 non-text-UI threshold)
    wasn't computed at all. The mobile drawer gained a keyboard way to
    close but not full focus trapping (focus moving into it on open,
    returning to the trigger on close) — Escape-to-close closes the gap
    that mattered most without the larger, harder-to-verify-blind change.

With 16 days to the hackathon and iQOO being what's actually judged: 1–4
should be genuinely excellent; 6–9 should be honest, clean, and lighter-touch
rather than rushed to false completeness.
