"""runtime/setup_state.py — Phase C7.

Tracks the onboarding *journey* — first_run / in_progress / complete —
not any process's runtime state. Deliberately a separate file
(~/.sam_data/setup_state.json) from Settings' own
~/.sam_data/settings.yaml: SetupState and RuntimeStatus are different
layers (docs/RUNTIME_BRIDGE_DESIGN.md §C), and sharing one file would
make that an accident of implementation rather than the design it
actually is. `selected_model` lives here too, not in Settings — it
records *what onboarding recommended and the user confirmed*, a journey
fact, separate from `Settings.primary_model`, which is *the live
runtime's current choice* and can change afterwards via the Brain page
without that having anything to do with setup having completed.
"""

from __future__ import annotations

import json
from pathlib import Path

VALID_STATES = {"first_run", "in_progress", "complete"}
DEFAULT_PATH = Path.home() / ".sam_data" / "setup_state.json"


def read_setup_state(path: Path | None = None) -> dict:
    """Never raises. A missing or unreadable/corrupt file is treated the
    same as a genuinely fresh install (first_run) — mirrors Settings'
    own don't-crash-on-a-bad-file philosophy rather than inventing a
    different one here."""
    path = path or DEFAULT_PATH
    if not path.exists():
        return {"state": "first_run", "selected_model": None}
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {"state": "first_run", "selected_model": None}
    if not isinstance(data, dict) or data.get("state") not in VALID_STATES:
        return {"state": "first_run", "selected_model": None}
    data.setdefault("selected_model", None)
    return {"state": data["state"], "selected_model": data["selected_model"]}


def write_setup_state(state: str, selected_model: str | None = None, path: Path | None = None) -> dict:
    """Raises ValueError on an invalid state -- the one case this
    *should* surface loudly, since it means a caller (CLI, future UI)
    passed something that isn't one of the three real states, not that
    the file on disk is merely absent or stale."""
    if state not in VALID_STATES:
        raise ValueError(f"{state!r} is not one of {sorted(VALID_STATES)}")
    path = path or DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"state": state, "selected_model": selected_model}
    path.write_text(json.dumps(data))
    return data
