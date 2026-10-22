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
the installer rechecks each stage, reuses a supported environment, and skips
dependency installation when every selected group already satisfies the
manifest's package constraints. It also skips models already installed and
preserves user settings and data. If replacement-environment dependency installation fails, the previous
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
large language models. First run guides the user to install the official
Ollama macOS app, start it or connect to a configured endpoint, then choose a
model. Downloads require a separate confirmation that explains storage and
network use; progress, cancellation, and retry are available in onboarding and
Settings.

The app bundles core Python dependencies and pip as a package-management tool.
Voice, vision, memory, and integrations are not installed by default. A user
can choose an optional capability in Diagnostics; its manifest-constrained
packages are installed under `~/.sam_data/python-packages`, outside the
read-only app bundle. Capability status reports missing Python packages and
OS prerequisites separately. The Vision group also installs Chromium into the
user's Playwright cache. A system prerequisite such as PortAudio still needs
the documented macOS package-manager route.

Runtime files use stable paths: the app bundle contains the interpreter,
application source, and core site-packages; `~/.sam_data/desktop-runtime.json`
stores runtime paths; `~/.sam_data/logs` stores logs; and settings, memory,
credentials, Ollama models, and optional packages remain in user-owned
locations. Replacing the app with a newer DMG refreshes bundled resources and
preserves user data. A damaged runtime config is backed up and reconstructed
from the current app resources; missing bundle resources produce a repair
message to reinstall the app.

The default app/DMG is unsigned and architecture specific; this implementation
path has not been validated as a release. Consumer distribution currently
targets macOS only. Build arm64 and x86_64 artifacts on matching packaging
machines; no universal binary or Windows/Linux consumer packages are declared.
Linux backend setup and Windows MSI remain source/developer paths. Version 1
uses manual DMG replacement for updates; it has no in-app updater.

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
manifest constraints. In a consumer install, packages go to the writable
per-user capability directory. OS prerequisites still require the platform
package manager.

Use the platform source setup script again to repair an environment. It does
not remove prior virtual environments, user settings, credentials, or Ollama
models. See the compatibility report in Desktop Diagnostics for concrete
missing package and prerequisite guidance.

## Verification status

This document describes the implemented paths and intended behavior. It does
not assert that native builds, consumer packaging, installers, or first launch
have been executed successfully. Those checks must be performed separately on
the target operating systems.
