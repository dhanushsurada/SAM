# SAM Desktop — combined delivery (native shell + runtime bridge C1–C7)

Unzip at the repository root. Supersedes `sam-desktop-combined.zip` from
last round — this is the complete current state, native shell through C7.

## New this round (C6, C7)

- `runtime/setup_state.py` — the onboarding-journey state
  (`first_run`/`in_progress`/`complete` + `selected_model`), persisted at
  `~/.sam_data/setup_state.json`. Deliberately not in `settings.yaml` —
  it's a different layer from both `RuntimeStatus` and `Settings`
  (docs/RUNTIME_BRIDGE_DESIGN.md §C).
- `sam_cli.py setup-state get|set --json` — same CLI-bridge pattern as
  `ollama`, added for the same reason: Rust shells out here rather than
  touching the JSON file directly, so what counts as a valid state has
  exactly one home even though the file itself is simple.
- `runtime.rs` gains `setup_state_get`/`setup_state_set`; `native.ts`
  gains `getSetupState`/`setSetupState`.
- `interfaces/desktop/src/stores/runtime.tsx` — the one shared
  runtime/model/setup-state store (`RuntimeProvider`/`useRuntime()`),
  wired into `App.tsx` alongside the existing `TaskSessionProvider`.
  Polling is ref-counted: it only runs while at least one mounted
  component has called `useRuntimePolling()`, shared across however many
  are mounted at once, torn down when the last one unmounts — not a
  background timer the whole app pays for regardless of what's on
  screen.

Nothing yet *calls* `useRuntime()` — Onboarding, Settings, and
Permissions still don't consume it. That's C8/C9, not started.

## Verification (re-run fresh this round, not carried over)

| Layer | Result |
|---|---|
| Python (`setup_state.py` + everything from C1–C4) | **152/152** offline checks — round-trip, corrupt-file, invalid-state, and CLI-subprocess paths for setup-state all actually executed |
| TypeScript (`runtime.tsx`, `App.tsx`, `native.ts`, and the full existing tree) | Real `tsc --noEmit`, full tree: **0 errors** |
| Rust (`runtime.rs`'s 2 new commands) | Unverified by execution, same as every other Rust command so far — no `cargo` in this sandbox |

## First run — unchanged from last round

```bash
cd interfaces/desktop
npm install
cd src-tauri && cargo check
cd ../../..
npm run tauri icon /path/to/SAM_LOGO.png   # (run from interfaces/desktop)
cd interfaces/desktop && npm run tauri dev
```

## Still open

C8 (wire Onboarding's steps to `useRuntime()`/`useSetupState`,
gate "Ready" on real health, stop showing terminal copy-paste for model
setup), C9 (Settings' "SAM Runtime" section). Everything else flagged in
`PHASE_C1-C3_REPORT.md` and `RUNTIME_BRIDGE_DESIGN.md` §I is exactly as
open as it was there.
