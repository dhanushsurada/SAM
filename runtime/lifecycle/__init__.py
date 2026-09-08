# Deliberately does NOT import from runtime.lifecycle.manager here.
# manager.py depends on runtime.health.status (for status()/health()), and
# runtime.health.status depends on runtime.lifecycle.specs/state —
# importing manager at package-init time would make importing
# runtime.lifecycle.specs (a dependency of runtime.health.status) trigger
# this __init__, which would import manager, which would import
# runtime.health.status again while it's still mid-initialization: a
# circular import. specs/state have no such dependency, so they're safe to
# re-export here. Get SAMRuntime from `runtime` (top-level) or
# `runtime.lifecycle.manager` directly.
from runtime.lifecycle.specs import ProcessSpec, default_specs
from runtime.lifecycle.state import is_pid_alive, read_state, pid_matches_expected

__all__ = ["ProcessSpec", "default_specs", "is_pid_alive", "read_state", "pid_matches_expected"]
