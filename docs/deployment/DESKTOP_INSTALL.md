# SAM Desktop installation and recovery

SAM ships as a consumer installer on **Windows (NSIS .exe), macOS (DMG) and
Linux (.deb / AppImage)**. Each embeds a managed Python runtime and the core
dependency group, so end users install nothing else except Ollama (guided from
first run). Source-based developer setups (`setup.sh`, `setup_linux.sh`,
`setup_windows.ps1`) remain available. End-user instructions are in
[`INSTALL.md`](../../INSTALL.md); this document is the maintainer reference.

## Pipeline

```
scripts/stage_runtime.py        build the relocatable runtime on the target OS/arch
  -> source/  python/  site-packages/  bundle.json   (resources/sam-runtime)
scripts/smoke_test_runtime.py   start API via sam_cli, hit /api/iqoo/health + /api/environment, stop, assert port freed
tauri build                     per-OS targets from tauri.<os>.conf.json
  Windows  NSIS setup.exe  (per-user install, no UAC, WebView2 bootstrapper embedded,
                            installer-hooks.nsh stops running SAM before upgrade/uninstall,
                            asks before deleting ~/.sam_data)
  macOS    .app + .dmg     (hardened runtime, Entitlements.plist, Info.plist usage strings,
                            scripts/macos_sign_runtime.sh signs nested Mach-O when a Developer ID is set)
  Linux    .deb + AppImage
.github/workflows/release.yml   matrix build + install-test + SHA256SUMS.txt + draft GitHub release
.github/workflows/ci.yml        pytest (3.11/3.12), frontend build, cargo check x3 OS, runtime smoke x3 OS, script lint
scripts/install.sh|install.ps1  one-line bootstrap installers (checksum-verified)
```

Release: `git tag v0.1.0 && git push --tags`. Locally on the target OS:
`cd interfaces/desktop && npm ci && npm run package`.

Asset names (consumed by the bootstrap scripts): `SAM_<ver>_windows-x86_64-setup.exe`,
`SAM_<ver>_macos-arm64.dmg`, `SAM_<ver>_macos-x86_64.dmg`,
`SAM_<ver>_linux-x86_64.deb`, `SAM_<ver>_linux-x86_64.AppImage`, `SHA256SUMS.txt`.

Optional signing secrets (builds are unsigned without them): `APPLE_CERTIFICATE`
(base64 .p12), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`,
`APPLE_ID`, `APPLE_PASSWORD`, `APPLE_TEAM_ID`. Windows Authenticode signing is
not wired up yet (needs a purchased certificate and a `signCommand`).

Runtime behaviour worth knowing: single instance (a second launch focuses the
first); quitting from the tray stops the Python backend (so installers can
replace files); the Quick Assistant shortcut is Cmd+Shift+Space on macOS and
Ctrl+Shift+Space elsewhere; Ollama is located via PATH and the official install
locations, so it is detected immediately after installation.

Not implemented: in-app auto-update (needs a signing key and update endpoint),
Windows ARM64 and Linux ARM64 builds, a universal macOS binary.

## Supported policy and environment manager

[`compatibility/manifest.json`](../../compatibility/manifest.json) is the
policy source for Python minors, dependency groups, required tools, OS
constraints, and feature-specific system prerequisites.
`runtime/compatibility.py` selects a Python version compatible with pinned
dependency constraints; `runtime/environment_manager.py` reports detected OS,
architecture, hardware, disk space, tools, dependency versions, optional
capabilities, and setup progress. Optional voice, vision, memory, and
integration groups are installed only when selected. Core setup does not
require those optional groups.

The manager's `/api/environment` report is local-only and excludes credential
values. Diagnostics and onboarding consume it; missing optional dependencies
are shown as unavailable without preventing the core API from starting.
Voice and Telegram process startup return a concrete dependency recovery
message when their required optional dependencies are absent.

## macOS developer setup

```sh
./setup.sh
```

This path requires macOS 14 or later, Homebrew, Apple Command Line Tools,
Node/npm, Rust, and a supported Python (3.11 or 3.12 as declared in the
manifest). Setup offers supported prerequisites rather than installing an
arbitrary newest Python. Ollama is installed through the manifest's macOS
Homebrew cask route and setup waits for its API to become ready. Model choices
come from existing settings; setup asks before downloading each missing model.
Desktop startup is owned by the Tauri app, not a competing launch agent.

The Python environment is `.venv`. If it is incomplete or uses an unsupported
interpreter, setup renames it to a dated `.backup-*` directory before creating
a compatible replacement. The backup is retained. Dependency, model, and
desktop-build steps are recorded under `~/.sam_data/environment_setup.json`.
Failed steps are marked blocked with a timestamp and attempt count. Rerunning
the installer rechecks each stage, reuses a supported environment, and skips
dependency installation when every selected group already satisfies the
manifest's package constraints. It also skips models already installed and
preserves user settings and data. If replacement-environment dependency installation fails, the previous
environment is restored when one exists and the failed candidate is retained
for diagnosis. This is safe rerun recovery; it does not claim to resume a
partially downloaded package at byte offset.

## Optional capabilities in the installed app

Voice, vision, memory and integrations are not installed by default. Choose a
capability in Diagnostics; its manifest-constrained packages install under
`~/.sam_data/python-packages` (outside the read-only app bundle). Vision also
installs Chromium into the user's Playwright cache. A system prerequisite such
as PortAudio still needs the platform package manager.

Runtime files use stable paths: the app bundle holds the interpreter,
application source and core site-packages; `~/.sam_data/desktop-runtime.json`
stores runtime paths (rebuilt automatically if damaged); `~/.sam_data/logs`
holds logs; settings, memory, credentials, Ollama models and optional packages
stay in user-owned locations. Installing a newer version over the old one
refreshes bundled resources and preserves user data.

## Linux developer setup

`setup_linux.sh` supports Debian and Ubuntu on architectures listed in the
manifest, using `apt-get`. It provisions a compatible Python and installs
selected dependency groups. Linux support currently covers the Python backend
only; it does not build or install Tauri and does not configure automatic
startup. Start the backend manually with `sam_cli.py start api` or the
documented developer command.

## Windows developer setup

`setup_windows.ps1` uses the same manifest-based Python selection and
dependency groups, preserves an unusable virtual environment as a backup, and
builds/installs the Tauri MSI. The app owns API process startup; an older
scheduled task is disabled and preserved to prevent duplicate process
managers. Windows is a source-based developer path; no relocatable Windows
consumer package is provided here.

## User configuration and recovery

Settings live at `~/.sam_data/settings.yaml` (Windows user home equivalent),
onboarding state at `~/.sam_data/setup_state.json`, and setup progress at
`~/.sam_data/environment_setup.json`. Settings are schema-versioned; migration
backs up the previous file before an atomic update and preserves unknown keys.
Desktop settings use the local-only `/api/settings` endpoint, validate values,
and redact credentials on reads. Model downloads use Ollama's resumable pull
stream; the UI shows progress and errors and setup never starts a download
without confirmation. Active downloads can be cancelled from Onboarding or
Settings; closing the gateway stream lets a later Ollama retry reuse partial
download data. Diagnostics offers explicit dependency-group repair using
manifest constraints. In a consumer install, packages go to the writable
per-user capability directory. OS prerequisites still require the platform
package manager.

Use the platform source setup script again to repair an environment. It does
not remove prior virtual environments, user settings, credentials, or Ollama
models. See the compatibility report in Desktop Diagnostics for concrete
missing package and prerequisite guidance.

## Verification status

The Claude handoff reports a successful Linux x86_64 runtime stage, smoke
test, Tauri `cargo check`, frontend build, and offline test run. Those results
were not reproduced in this checkout. Windows- and macOS-specific builds,
installers, signing, and first-launch behavior also remain unverified here;
use the CI workflows and target machines before publishing a release.
