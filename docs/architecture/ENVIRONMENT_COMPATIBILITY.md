# SAM environment and compatibility manager

`runtime/environment_manager.py` is the shared local environment service.
Installers call its `preflight` command; support and diagnostic screens can
use `discover`, `capabilities`, and `diagnose`. It reads policy from
`compatibility/manifest.json`, so Python/tool versions and core versus
optional dependency groups have one source of truth.

The manager is read-only during discovery. It reports OS and CPU architecture,
available Python executables, installed tools and versions, package-group
availability, memory where the operating system permits inspection, Ollama
reachability and pulled models, audio modules, and browser automation support.
It does not install packages, start Ollama, or download models. The
`resolve-dependencies --group voice` command prints the selected requirements;
the installer remains responsible for asking before an installation.

## Configuration and recovery

User settings carry `sam_settings_schema_version`. Older settings are backed
up byte-for-byte as `~/.sam_data/settings.yaml.schema-0.bak` before an atomic
migration. Unknown settings and model selections are retained. A settings file
from a newer schema is left untouched and produces an actionable update error.
The tracked repository defaults are never migrated in place.

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
```

The report distinguishes install-critical groups from optional voice,
memory, and integration groups. Optional capability gaps include a recovery
hint and do not make an otherwise compatible installation fail preflight.
The macOS source installer still requires its declared desktop build tools.
