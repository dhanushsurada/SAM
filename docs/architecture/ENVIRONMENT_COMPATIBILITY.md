# SAM environment and compatibility manager

`runtime/environment_manager.py` is the shared local environment service.
Installers call its `preflight` command; support and diagnostic screens can
use `discover`, `capabilities`, and `diagnose`. It reads policy from
`compatibility/manifest.json`, so Python/tool versions, dependency groups,
and feature-specific system prerequisites have one source of truth.
Installers select the default `core` group and prompt before adding `voice`,
`vision`, `memory`, or `integrations`.

The manager is read-only during discovery. It reports OS and CPU architecture,
available Python executables, installed tools and versions, package-group
availability including version compatibility, feature-specific OS
prerequisites, memory where the operating system permits inspection, Ollama
reachability and pulled models, audio modules, and browser automation support.
It does not install packages, start Ollama, or download models. The
`resolve-dependencies --group voice --format requirements` command prints
pip requirement arguments for the selected group; without `--group`, the
manager resolves the manifest's defaults. `system-dependencies --group voice`
reports platform prerequisites. The installer remains responsible for asking
before installation.

## Configuration and recovery

User settings carry `sam_settings_schema_version`. Older settings are backed
up byte-for-byte as `~/.sam_data/settings.yaml.schema-0.bak` before an atomic
migration. Unknown settings and model selections are retained. A settings file
from a newer schema is left untouched and produces an actionable update error.
The tracked repository defaults are never migrated in place. Each schema step
must have an explicit migration registered in `runtime/config_migrations.py`;
SAM refuses to advance a file if a step is missing.

Setup progress is recorded atomically in
`~/.sam_data/environment_setup.json`. A rerun can inspect completed, started,
or blocked steps. The installer continues to use idempotent operations and
never deletes or replaces the existing settings file or model store to
recover. Corrupt recovery metadata is preserved and reported for inspection.

## Commands

Run from the SAM checkout:

```sh
python runtime/environment_manager.py discover
python runtime/environment_manager.py capabilities
python runtime/environment_manager.py diagnose
python runtime/environment_manager.py resolve-dependencies --group core
python runtime/environment_manager.py resolve-dependencies --group vision --format requirements
python runtime/environment_manager.py system-dependencies --group voice
```

The report distinguishes core from optional voice, vision, memory, and
integration groups. Optional capability gaps include a recovery
hint and do not make an otherwise compatible installation fail preflight.
The macOS source installer still requires its declared desktop build tools.
Linux remains scoped to Debian/Ubuntu with apt and does not configure
automatic startup. Windows and macOS use the same Python and package-group
policy, with native prerequisite installation handled by each installer.
