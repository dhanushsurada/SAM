# SAM Desktop (Phase 5)

The full SAM product UI — not `frontend/` (that's VEDA, a different product
for a different hackathon) and not `interfaces/web/` (SAM's existing narrow
iQOO phone client, left untouched).

See `../../docs/frontend/PHASE5_PLAN.md` for the full plan: capability map,
architecture decisions, directory structure, page inventory, design system,
the real-vs-demo backend boundary, and implementation order.

## Setup

For a supported macOS developer install, run the repository-level
`../../setup.sh`; it checks the compatibility manifest, creates the Python
environment, installs prerequisites with consent, and builds/opens the Tauri
app. This requires macOS 14+, Python 3.11 or 3.12, Node/npm, Rust, and Apple
Command Line Tools. Setup preserves an incompatible environment as a dated
backup before recreating it; rerunning setup reuses a supported environment,
repairs dependencies through the selected manifest groups, and skips models
already present in Ollama.

The separate macOS consumer packaging route is `npm ci` followed by
`npm run package:macos-consumer` from this directory. It requires `uv`, network
access, and native build tools on the packaging Mac. It stages a managed Python
runtime and core dependencies into the app resources and creates an app and
DMG. The app writes its runtime paths under `~/.sam_data`; uninstalling the
app removes the application bundle but preserves settings, credentials, and
models in user data. The current output is unsigned and is not a trusted public
release until signing and notarization are configured.

Core Python dependencies are installed by default; voice, vision, memory,
and integration dependencies are optional prompts. Select voice when
microphone capture is needed (it may install PortAudio); select vision to
install Playwright and its Chromium browser.

For frontend-only work:

```bash
cd interfaces/desktop
npm ci
npm run dev
```

The API routes use the configured SAM gateway; `npm run dev` alone does not
start the backend.

## About `src/types/react-shim.d.ts`

The project now includes real React and Tauri type dependencies in its lockfile.
Keep the shim declarations only where they model APIs that the installed
packages do not expose to the type checker; do not delete or retain them based
on the old “install the real packages first” notes without checking the
current TypeScript build.

## What this app is

A web UI served by Vite in a browser tab, now also loadable inside a native
macOS shell — see `src-tauri/` and `src-tauri/NATIVE_SHELL_NOTES.md`. The
shell wraps this same app; it doesn't fork it. What changed with Phase 5
was the product structure: SAM is the product, the Brain and Hands are what
it's made of, and the iQOO workspace is one workflow built on them. The
browser is a single card on the Hands page, not the frame around the app —
and now, running natively, there is no browser frame around it at all.

## Native shell (Agent 1 — `agent/desktop-product`)

A Tauri v2 shell in `src-tauri/` wraps this app: native
window, Dock/menu-bar-resident lifecycle, a tray icon, a global-shortcut
Quick Assistant window (`src/features/quick-assistant/`), a notification
bridge, a startup preference, and a configured Python runtime bridge. The
native Rust build has not been verified in the current environment because
`cargo`/`rustc` are unavailable. Full status, the framework decision and why, the
permissions matrix, and what's still open are all in
`src-tauri/NATIVE_SHELL_NOTES.md` — read that before extending this layer
further.

## What's real vs. demo right now

Live backends include the task gateway (`/api/iqoo/*`), Brain/model controls
(`/api/models`), local settings read/write (`/api/settings`), and environment
capability reporting (`/api/environment`). Diagnostics and onboarding use live
environment/runtime data. Memory, Founder Mode, Skills, and Licensing still
contain demo-backed surfaces.
Full breakdown, with the exact remaining endpoints, is in `PHASE5_PLAN.md` §F.

## Status

All 10 steps of the plan's implementation order (`PHASE5_PLAN.md` §H) are
done, plus the Brain / desktop-correction pass
(`../../docs/BRAIN_MODEL_SELECTION_AND_DESKTOP.md`).

- Design tokens (light + dark, two values corrected by computed WCAG
  contrast — see §H step 10), globals, shared components (`Button`,
  `StatusPill`, `ModeBadge`, `EmptyState`, `PageHeader`, `Switch`)
- App shell — sidebar, top bar, routing, persisted theme toggle, a real
  mobile drawer, skip-to-content link, Escape-to-close
- Typed API client (`src/api/`) mirroring `interfaces/api/schemas.py`
  field-for-field, plus the `iqoo` and `brain` service layers and shared
  task-session state (`src/stores/taskSession.tsx`)
- **Live, on real backends:**
  - `/` Command Center — task input, gateway status, Brain summary
  - `/chat` — each message runs as a real task and SAM's reply is its
    outcome. Single-turn: the gateway gives the Brain no chat history, and
    there's no token streaming
  - `/tasks` — general task console with the lifecycle
    (understand, plan, execute, verify, result), live events, cancel, retry
  - `/brain` — installed models discovered from Ollama, active model,
    compatibility, and a selector that changes the real runtime Brain
  - `/iqoo` — the phone-to-PC workspace: gateway health and demo controls
  - `/connect` — trusted device pairing and revocation, notification-task routing, and task status via SAM Connect
- **`/hands`** — what SAM's Hands can do, read from the ReAct action table;
  only the vision/Whisper rows are probed (gateway health), Office Kit is
  listed as not implemented
- **`/memory`, `/founder-mode`, `/skills`, `/diagnostics`, `/licensing`,
  `/settings`** — Settings load and save through the local API; the live
  section shares runtime/model state and manages launch-at-login
- **`/onboarding`** — persisted first-run wizard with runtime/model controls
- `/models` no longer exists; it was the demo page the Brain page replaced

Two real bugs found and fixed while building the iQOO integration, and
two real WCAG contrast failures found and fixed in the final pass — all
four documented with the actual numbers in `PHASE5_PLAN.md` §H, not just
asserted. That file also says plainly what the accessibility pass did
*not* cover (no real browser/screen-reader testing was possible here,
border contrast wasn't computed, the mobile drawer has no full focus trap)
— worth reading before treating this as a finished audit rather than a
solid first pass.

**Not done, and not pretended to be:** every backend endpoint this UI
would need to stop being a demo is listed with request/response shape and
priority in `PHASE5_PLAN.md` §F. Nothing in this app claims a capability
the repository doesn't actually have — the same rule now applies to
`src-tauri/`: see its own notes for exactly what's implemented, what's
unverified, and what's simply not started.
