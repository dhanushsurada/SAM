# Native shell drop-in — manifest

Unzip this at the repository root (same level as `interfaces/`, `docs/`,
`README.md`). Every path below is relative to that root. Branch:
`agent/desktop-product`, per the brief — nothing here touches `main`,
Android, or the cross-device protocol.

This supersedes the first drop from earlier in this session — don't merge
both, use this one. What changed since the first drop: the global-shortcut
handler had a real bug (`event.state()` should be `event.state`), found via
web search against Tauri's own docs/source and fixed; notifications now go
through the notification plugin's own JS bindings instead of a custom Rust
command; every new/modified `.tsx`/`.ts` file is now `tsc`-checked against
the real component tree, not just hand-written; and a new `/permissions`
page was added. Full detail in `interfaces/desktop/src-tauri/NATIVE_SHELL_NOTES.md`
— read that first, this file is just the map.

## New files

```
interfaces/desktop/src-tauri/Cargo.toml
interfaces/desktop/src-tauri/build.rs
interfaces/desktop/src-tauri/.gitignore
interfaces/desktop/src-tauri/tauri.conf.json
interfaces/desktop/src-tauri/capabilities/default.json
interfaces/desktop/src-tauri/src/main.rs
interfaces/desktop/src-tauri/icons/README.md
interfaces/desktop/src-tauri/NATIVE_SHELL_NOTES.md
interfaces/desktop/src/lib/native.ts
interfaces/desktop/src/types/tauri-shim.d.ts
interfaces/desktop/src/features/quick-assistant/QuickAssistantApp.tsx
interfaces/desktop/src/features/permissions/PermissionsPage.tsx
```

## Modified files (shown here in full — replace, don't merge by hand)

```
interfaces/desktop/src/main.tsx       — dispatches by Tauri window label
interfaces/desktop/src/app/routes.ts  — adds the /permissions route entry
interfaces/desktop/src/app/router.tsx — registers PermissionsPage
interfaces/desktop/package.json       — adds @tauri-apps/api,
                                         @tauri-apps/plugin-notification,
                                         @tauri-apps/cli, "tauri" script
interfaces/desktop/README.md          — corrected the "no native shell"
                                         line, added a section pointing at
                                         src-tauri/
```

Nothing else in the repository was touched — no Core changes, no route
renames, no `iqoo` → `gateway` renaming attempted (the PDR's own note says
that's a separate, older, not-yet-reconciled tree; out of scope here).

## First run, in order

```bash
cd interfaces/desktop
npm install
cd src-tauri && cargo check     # the real test — read errors here first,
cd ..                           # they're clearer than tauri dev's
npm run tauri icon /path/to/SAM_LOGO.png
npm run tauri dev
```

`cargo check` is still the thing nothing here has been through. Everything
TypeScript has at least been `tsc`-checked against the real component
tree this round — see NATIVE_SHELL_NOTES.md's verification table for
exactly what that does and doesn't guarantee.
