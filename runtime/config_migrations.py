"""Safe, versioned migrations for user-owned SAM settings files."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import yaml


SETTINGS_SCHEMA_VERSION = 1
SCHEMA_KEY = "sam_settings_schema_version"


def _migrate_0_to_1(values: dict) -> dict:
    """Introduce the schema marker; preserve all existing user-owned keys."""
    migrated = dict(values)
    migrated[SCHEMA_KEY] = 1
    return migrated


# Add one explicit, reversible-in-concept transformation per old schema when
# configuration changes. Missing steps fail closed instead of silently
# labeling an unconverted file as current.
MIGRATIONS = {0: _migrate_0_to_1}


class SettingsMigrationError(RuntimeError):
    pass


def migrate_settings_file(path: Path) -> dict:
    """Upgrade an old settings file atomically and retain a byte-for-byte backup.

    Unknown keys and user-selected values are preserved. A future schema is
    rejected without writing so an older SAM version cannot downgrade it.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
        values = yaml.safe_load(raw) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise SettingsMigrationError("Cannot read settings file {}: {}".format(path, exc)) from exc
    if not isinstance(values, dict):
        raise SettingsMigrationError("Settings file {} must contain a YAML mapping".format(path))
    current = values.get(SCHEMA_KEY, 0)
    if not isinstance(current, int) or current < 0:
        raise SettingsMigrationError("Invalid {} in {}".format(SCHEMA_KEY, path))
    if current > SETTINGS_SCHEMA_VERSION:
        raise SettingsMigrationError(
            "Settings schema {} is newer than SAM supports ({}); update SAM before opening this file".format(
                current, SETTINGS_SCHEMA_VERSION))
    if current == SETTINGS_SCHEMA_VERSION:
        return values

    backup = path.with_name(path.name + ".schema-{}.bak".format(current))
    if not backup.exists():
        try:
            with backup.open("xb") as stream:
                stream.write(raw)
        except FileExistsError:
            pass
        except OSError as exc:
            raise SettingsMigrationError("Cannot preserve settings backup {}: {}".format(backup, exc)) from exc

    migrated = dict(values)
    while current < SETTINGS_SCHEMA_VERSION:
        migration = MIGRATIONS.get(current)
        if migration is None:
            raise SettingsMigrationError(
                "No safe settings migration is registered from schema {} to {}".format(
                    current, current + 1))
        migrated = migration(migrated)
        current += 1
    temporary = path.with_name(path.name + ".migration.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as stream:
            yaml.safe_dump(migrated, stream, default_flow_style=False, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(path))
    except (OSError, yaml.YAMLError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise SettingsMigrationError("Could not migrate settings {}; original backup is at {}: {}".format(
            path, backup, exc)) from exc
    return migrated
