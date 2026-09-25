# Native shell — status (Agent 1, agent/desktop-product)

Written against the repo as of the `SAM-main` zip dated 2026-09-20, in a
sandbox with no `cargo`/`rustc`, no macOS, and no network for `npm`/`cargo`
(web search was available and used — see Verification below). Grounded
against `docs/frontend/PHASE5_PLAN.md`, `interfaces/desktop/README.md`, and
the Master PDR (2026-09-23) — where this doc adds detail rather than
repeats them, it says so instead of quietly duplicating.

## Verification status — read this before trusting anything below

| Layer | Verified how | Confidence |
|---|---|---|
| `src/lib/native.ts` | Real `tsc --noEmit`, strict, against this project's own `tsconfig.json` options. | Real, partial — types check; behavior doesn't run anywhere here. |
| `src/main.tsx`, `QuickAssistantApp.tsx`, `PermissionsPage.tsx`, `routes.ts`, `router.tsx` | `tsc`-checked against the **real, complete `src/` tree** — `Button`, `PageHeader`, `ModeBadge`, `StatusPill`, `taskSession`, `phase.ts`, `api/types.ts` are the genuine files, not stand-ins, so calls into them are checked against real prop/return shapes. React/JSX plumbing itself (`react`, `react-dom`, `react-router-dom`, `react-icons/fi`) is stubbed loosely on purpose — that's not where real bugs tend to hide, and a precise `@types/react` recreation risked masking real errors behind a shim bug more than it added confidence. Passed clean, zero errors, across the whole tree. | Real for structure and API usage; not a substitute for an actual `npm install` + build + render. |
| Tauri config/Rust APIs (tray, menu, global-shortcut, window options, capabilities/permission strings, the notification plugin's JS bindings) | Checked against Tauri's own published docs and source this round — `tauri-apps/plugins-workspace` (v2 branch, actual `guest-js` source for the notification plugin), `v2.tauri.app` reference pages, and a real GitHub capabilities example — not just recalled. One real bug this found and fixed: the global-shortcut handler compared `event.state()` as a method call; it's a field, `event.state`. | Checked against documentation; still never compiled. `cargo check` is still the real test — see below. |

Tauri v2's plugin APIs have shifted across its own alpha→stable run, so
expect small drift even where sources agreed, not a wrong architecture.
Nothing here has run — checked-against-docs and checked-against-a-compiler
are different things, and only the second one is `cargo check`.

## Decision: Tauri v2, not Electron

Unchanged from the first pass — nothing in the repo or PDR pins a
native-shell framework (PDR §12: "using the selected native shell
architecture" reads as delegating the choice). Picked Tauri because the
existing UI is already React+TypeScript+Vite (Tauri wraps that directly,
no parallel main/renderer split to author), it has a smaller footprint and
lower idle memory than Electron (matters more than usual here — SAM is
meant to sit resident continuously, not open-use-close), and Rust next to
a Python Core doesn't create an illusion of one shared JS runtime either
way. Real trade-off: Tauri's plugin ecosystem is smaller than Electron's —
this round's `cargo`-less verification gap is exactly that trade-off
showing up, not a wrong call.

## What's implemented

- **Native window** wrapping the existing app unchanged — no fork, no
  second copy of the UI. `devUrl` points at the current Vite dev server
  (port 5173, confirmed in `vite.config.ts`); `frontendDist` at the
  existing `npm run build` output.
- **Resident lifecycle**: closing the main window hides it; Cmd+Q or tray
  → "Quit SAM" actually quits. Dock-icon reopen re-shows the main window.
  Deliberately kept the Dock icon (no `LSUIElement`) rather than going
  full menu-bar-only — the brief asks for both Dock presence and menu-bar
  operation, not one instead of the other.
- **Menu-bar (tray) icon** with Show SAM / Quick Assistant / Quit.
- **Global shortcut** (Cmd+Shift+Space) toggling a second, small,
  always-on-top **Quick Assistant** window — a real second window into
  the same app (own `TaskSessionProvider`, same real gateway), not a
  second frontend. `src/main.tsx` decides which tree to mount by reading
  the Tauri window **label**, not the URL — sidesteps needing SPA-fallback
  routing to work correctly for a second window.
- **Notifications**: `native.ts` calls `@tauri-apps/plugin-notification`'s
  own JS bindings (`isPermissionGranted`, `requestPermission`,
  `sendNotification`) directly, rather than a custom Rust command wrapping
  them — simpler, more idiomatic, and it's what those bindings are for.
  The Rust side still registers `tauri_plugin_notification::init()`, which
  is what makes the JS bindings work at all; only the redundant custom
  command was removed.
- **Quick Assistant UI**: single input, Enter to send, Escape to dismiss,
  reuses `submitTask`/`selectedTask`/`events` from the existing
  `taskSession` store and the real `Button`/`StatusPill` components — the
  same real gateway calls Command Center's quick input already makes, not
  a new task path.
- **Permissions page** (`/permissions`, new route, "system" nav group):
  two visibly separate sections rather than one flat list. **Desktop
  app** — Notifications, genuinely live: real status on load, a Request
  button that only appears when not yet granted, an explicit note when
  running in a plain browser tab (browser permission ≠ native app
  permission). **SAM Core** — Accessibility, Screen Recording, Microphone,
  each labeled with which SAM subsystem needs it and why, marked DEMO:
  there's no backend endpoint yet reporting Core's permission state, so
  "Not reported" is shown rather than invented. This operationalizes the
  permissions split this file already documented; previously that split
  existed only as prose here, not as a page.

## Known limitation, not hidden

Each Tauri window is its own JS runtime, so the Quick Assistant's
`TaskSessionProvider` is a **separate instance** from the main window's —
a task submitted from the palette won't appear in the main window's
Command Center/Tasks list until that window re-fetches. The backend state
is shared and real either way (same gateway, same task IDs); only the
in-memory React list is per-window. Cross-window sync (broadcasting a
Tauri event on submit, or moving session state behind a Rust-side store)
is the natural next step — not attempted, to keep this to what could
actually be reasoned about carefully rather than rushed.

## Permissions — two separate sets, now a real page, still worth restating

The native shell itself needs **no macOS Accessibility or Screen
Recording grant** — windows, a tray icon, a global shortcut and a
notification are all ordinary app-level APIs. macOS prompts once,
automatically, on first notification request; nothing to build for that.

**Accessibility, Screen Recording and Microphone belong to the Python
backend** (`hands/control` → PyAutoGUI, `hands/vision` → screen reading,
`ears/` → wake word + Whisper) — a separate process, granted separately in
System Settings, not requestable or checkable from this Tauri shell. The
Permissions page above now reflects exactly this split instead of implying
the desktop app is what's asking for all of it.

## Setup, once this is on a real Mac

```bash
cd interfaces/desktop
npm install                       # brings in @tauri-apps/api,
                                   # @tauri-apps/plugin-notification,
                                   # @tauri-apps/cli
npm run tauri icon /path/to/SAM_LOGO.png   # see src-tauri/icons/README.md
cd src-tauri && cargo check       # the real test of everything above —
                                   # do this before `tauri dev`
cd ..
npm run tauri dev
```

If `src/types/react-shim.d.ts` (referenced by the existing README) is
present in your actual checkout, leave it — unrelated to
`tauri-shim.d.ts`, which only stubs `@tauri-apps/api` and
`@tauri-apps/plugin-notification` and should be deleted once `npm install`
brings the real packages in (a comment in the file says so).

## Not done — flagged, not silently skipped

- Quick Assistant cross-window state sync (above).
- Permissions page: SAM Core rows are informational only — no backend
  endpoint exists yet to make them live. Contract this page assumes, for
  whoever builds that endpoint: a status per permission
  (`granted`/`denied`/`not-determined`/`unknown`), reported by SAM Core
  over the API, refreshed at least on page load.
- Onboarding tie-in: requesting/explaining native permissions as part of
  first run, rather than only the browser-can't-verify copy the existing
  `/onboarding` route already has, and rather than a separate page the
  user has to go find.
- Auto-launch-at-login is wired at the Rust/plugin level
  (`tauri-plugin-autostart`) but has no Settings UI toggle yet.
- Custom inset/hidden titlebar and any vibrancy/blur — deliberately left
  at Tauri's plain default `titleBarStyle` to keep the unverified surface
  smaller; a reasonable next visual pass once the basics compile.
- Code signing / notarization — `identifier` in `tauri.conf.json` is a
  placeholder (`dev.sam.desktop`); needs a real reverse-DNS identifier
  before any signed build.
- Production build has not been generated or manually tested on real
  hardware — PDR/Agent-1 "done criteria" items, both still open, both
  needing a real Mac to close out.

## One UI/UX reference note

Of the two UI reference images supplied, the "Dashboard" one leans heavily
glassmorphic (frosted floating panels) — worth citing selectively for the
**active/executing holographic states** PDR §7.1 describes, not as a
template for the calm/idle base UI, which the PDR itself says should
avoid "excessive glassmorphism." The other ("Coders" management UI) reads
as the generic SaaS-dashboard look §7 says to avoid outright. Neither
looks like it was meant as a literal target — noting the distinction so
it doesn't get treated as one by accident later.
