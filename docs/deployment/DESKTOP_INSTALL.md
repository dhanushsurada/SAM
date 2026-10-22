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
Failed steps are marked blocked with a timestamp and attempt count. Rerunning
the installer repeats its idempotent setup stages, reuses a supported
environment, skips models already installed, and preserves user settings and
data. If replacement-environment dependency installation fails, the previous
environment is restored when one exists and the failed candidate is retained
for diagnosis. This is safe rerun recovery; it does not claim to resume a
partially downloaded package at byte offset.

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
not bundled in the initial consumer package. The default app/DMG is unsigned
and architecture specific; this implementation path has not been validated as
a release. Consumer distribution currently targets macOS only. Linux backend
setup and Windows MSI remain source/developer paths.

For Developer ID signing and notarization, install Xcode Command Line Tools
and configure `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` (an
app-specific password), and `APPLE_TEAM_ID` in the packaging shell, then run
from the repository root:

```sh
scripts/package_macos_signed_release.sh
```

The wrapper packages with Tauri signing enabled, submits the DMG to Apple's
notary service, waits for acceptance, and staples the ticket. Keep credentials
outside the repository. arm64 and x86_64 require separate packaging runs.

The app-only uninstaller is `scripts/uninstall_macos_consumer.sh`. It removes
the app bundle and leaves `~/.sam_data`, downloaded models, settings, and
credentials intact. Passing `--remove-user-data` requests full removal and
requires typing the complete data path. Ollama and its model store are retained
in either case. Installing a newer app over the old app is the supported
upgrade path; the stable user data directory is preserved. There is no
in-app updater or automatic runtime migration beyond settings schema migrations.

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
manifest constraints; OS prerequisites still require the platform package
manager.

Use the platform source setup script again to repair an environment. It does
not remove prior virtual environments, user settings, credentials, or Ollama
models. See the compatibility report in Desktop Diagnostics for concrete
missing package and prerequisite guidance.

## Verification status

This document describes the implemented paths and intended behavior. It does
not assert that native builds, consumer packaging, installers, or first launch
have been executed successfully. Those checks must be performed separately on
the target operating systems.
