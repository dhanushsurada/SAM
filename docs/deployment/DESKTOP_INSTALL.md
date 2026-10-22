# SAM Desktop installation and recovery

SAM currently has two macOS paths with different purposes: a source-based
developer setup and a separately built consumer app/DMG. The consumer bundle
path is implemented in packaging code but has not been built or validated in
this change. Linux and Windows remain source-based paths described below.

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
Rerunning setup reuses an appropriate environment, repairs selected packages,
skips models already installed, and preserves user settings and data.

## macOS consumer app and DMG

On a packaging Mac with `uv`, Node/npm, Rust, Xcode Command Line Tools, and
network access:

```sh
cd interfaces/desktop
npm ci
npm run package:macos-consumer
```

The packaging script provisions a managed Python runtime using the manifest's
preferred supported version, installs the core dependency group, and stages
SAM source and dependencies as Tauri resources. Tauri bundles the resources
inside the app and emits an `.app` and `.dmg`; first launch creates
`~/.sam_data/desktop-runtime.json` with paths derived from the installed app,
then starts the API automatically. Existing API endpoint configuration is
preserved when a consumer app initializes its bundled paths.

The package uses the current Mac architecture and does not bundle Ollama or
large language models. Users still need Ollama installed and must select or
download models through setup/onboarding. Optional Python feature groups are
not bundled in the initial consumer package. The generated app/DMG is unsigned
by this repository configuration; Developer ID signing and notarization must
be configured before public distribution. No standalone consumer installer
is claimed ready until packaging, first launch, upgrade, and uninstall flows
have been exercised on a clean Mac.

Uninstalling the app bundle does not delete `~/.sam_data`, downloaded models,
settings, or credentials. This preserves user data across reinstallations;
users who want a full data removal must separately remove that directory.

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
without confirmation.

Use the platform source setup script again to repair an environment. It does
not remove prior virtual environments, user settings, credentials, or Ollama
models. See the compatibility report in Desktop Diagnostics for concrete
missing package and prerequisite guidance.

## Verification status

This document describes the implemented paths and intended behavior. It does
not assert that native builds, consumer packaging, installers, or first launch
have been executed successfully. Those checks must be performed separately on
the target operating systems.
