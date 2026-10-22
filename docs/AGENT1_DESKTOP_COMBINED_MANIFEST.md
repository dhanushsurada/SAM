# SAM Desktop — combined delivery (native shell + runtime bridge C1–C7)

Unzip at the repository root. Supersedes `sam-desktop-combined.zip` from
last round — this is the complete current state, native shell through C7.

> **Historical delivery snapshot.** The “New this round”, verification, and
> remaining-work notes below record the state when the agent archive was
> delivered; they are not a current implementation checklist. Later work
> added runtime-backed onboarding, settings persistence, and user-controlled
> login startup. Current installation policy and validation status live in
> `docs/deployment/DESKTOP_INSTALL.md` and `interfaces/desktop/README.md`.

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

Since this snapshot, Onboarding and Settings consume the shared runtime
state. The `/api/settings` endpoint persists editable preferences locally,
while credentials are redacted and incognito remains session-only.
Permissions has not been converted into a runtime-backed settings surface.

Later installation work adds `/api/environment`, live Diagnostics and
onboarding compatibility details, safe virtual-environment backup/recreation,
and a separate macOS consumer packaging command. The consumer command stages
a managed Python runtime and core dependencies into Tauri resources; it is
packaging code only and remains unbuilt/unverified until run on a target Mac.
See `docs/deployment/DESKTOP_INSTALL.md` for current installation policy.

## Verification (re-run fresh this round, not carried over)

| Layer | Result |
|---|---|
| Python (`setup_state.py` + everything from C1–C4) | **152/152** offline checks — round-trip, corrupt-file, invalid-state, and CLI-subprocess paths for setup-state all actually executed |
| TypeScript (`runtime.tsx`, `App.tsx`, `native.ts`, and the full existing tree) | Real `tsc --noEmit`, full tree: **0 errors** |
| Rust (`runtime.rs`'s 2 new commands) | Unverified by execution, same as every other Rust command so far — no `cargo` in this sandbox |

## First run — snapshot instructions superseded

```bash
./setup.sh
```

On macOS, the developer installer selects a compatible Python from
`compatibility/manifest.json`, installs Ollama through its macOS Homebrew cask
when needed, builds the `.app`, and opens it. First native launch starts the
API and routes fresh installs to the persisted onboarding journey. The native
Rust build still needs validation on a machine with Cargo and Rust installed.

## Still open

The current desktop still needs native Rust build/launch and consumer DMG
verification. Public distribution also requires Developer ID signing and
notarization, which are not configured here.
Android/Connect, JEV responsibility boundaries, task-state synchronization,
and remaining Core features are tracked in their current workstream documents;
this historical delivery report does not redefine them.
