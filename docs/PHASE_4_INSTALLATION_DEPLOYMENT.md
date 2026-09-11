# Phase 4 — Installation, Deployment & Onboarding

Status: core logic implemented and offline-tested; **not complete** — real-
machine validation on all three platforms is still outstanding, and that's
disqualifying, not a formality. This is SAM-as-a-whole scope, not an
official iQOO competition phase — see `docs/iqoo/PROGRESS.md` for those.

## What this phase covers

Making SAM installable, diagnosable, and repeatable by someone other than
the person who wrote it — without silently downloading large models,
introducing telemetry/cloud services, or corrupting an existing install on
a rerun. Practical companion: `docs/deployment/LOCAL_RUNTIME.md` covers
day-to-day `sam start`/`stop`/`doctor` usage; this doc covers the
installers themselves and how this phase got there.

## Audit findings (4.0)

Most of what a "Phase 4" audit usually turns up already existed and
worked: `sam_cli.py doctor`, the `runtime/lifecycle` manager, and
`config/settings.py`'s RAM-tiered model selection were all real,
functioning code, not gaps to fill. The actual gaps were narrower:

- `setup.sh` (macOS-only) wasn't idempotent against its own prior run —
  recreated `.venv` unconditionally, and unconditionally overwrote+reloaded
  a `launchd` agent even if one was already running, swallowing any
  failure from that reload silently.
- It also created a second, dead set of data directories relative to the
  repo itself, left over from before memory/founder_mode/skills all
  migrated to `~/.sam_data` — confirmed dead by reading those three
  modules directly, not assumed.
- No Linux installer existed at all.
- `setup_windows.ps1` existed but had never been run on real Windows.
- `python-dotenv` was a declared dependency with zero imports anywhere in
  the codebase.
- `sam doctor` confirmed Ollama was reachable and counted pulled models,
  but never checked whether the *specific configured* model was actually
  among them.

## What got built (4.2)

**`setup.sh` (macOS).** Reuses a valid `.venv` (checks for
`.venv/bin/python3`) instead of recreating it; rebuilds it if it looks
incomplete rather than leaving it broken. `launchd`: if the agent is
already loaded, unloads it before replacing the plist, reloads it, and
checks the real `launchctl` exit code instead of swallowing failures —
reports fresh-install vs. reinstall explicitly. Directory step repointed
from the dead repo-relative paths to the real `~/.sam_data/...` locations.
`ollama pull` and `pip install -r requirements.txt` were already
idempotent; left alone.

**`setup_windows.ps1` (Windows).** Same `.venv` reuse pattern, same
`~/.sam_data` target. Task Scheduler's existing `-Force` flag already
replaces a task of the same name safely — confirmed by its documented
semantics, not changed. **No PowerShell interpreter exists in the sandbox
this phase was built in** — these changes were reviewed, never even
syntax-checked, let alone run.

**`setup_linux.sh` (new).** Debian/Ubuntu (`apt`) only, explicit guard
against anything else rather than guessing. `portaudio19-dev` via `apt`,
Ollama via its official Linux install script, RAM read from
`/proc/meminfo`, same venv-reuse logic (its own real anchor-extracted
lines are what `tests/test_installer_venv_idempotency_offline.py` actually
executes — not a reimplementation). Deliberately no systemd unit in this
first version — start manually; autostart-on-boot is separate scope for
once the base path is validated on real hardware.

**`sam_cli.py doctor`.** One check added: `settings.primary_model` against
the model list already fetched for the "Ollama running" check — no
duplicate request. Reports PASS/FAIL/UNVERIFIED with an actionable
`ollama pull <model>` hint on FAIL. `cmd_doctor` otherwise untouched.

**`requirements.txt`.** `python-dotenv` removed — confirmed unused on two
independent full-repo passes (`.py`/`.md`/`.sh`/`.ps1`/`.yaml`, including
`load_dotenv`/`find_dotenv` under any alias), and confirmed no
`pyproject.toml`/`setup.cfg`/`.env` exists anywhere that could source it
indirectly.

## The `primary_model` guard fix

Not originally scoped — found while building the doctor check, because a
YAML-configured model kept getting silently overwritten. Root cause,
precisely: `Settings.__post_init__` runs `_load_yaml()` →
`_detect_hardware()` → `_select_model()`, and `_select_model()` had no
concept of "the user already chose one" — it overwrote `primary_model`
with a RAM-tier default whenever `detected_ram_gb` wasn't `None`, which
`_detect_hardware()` guarantees on macOS/Windows even when detection
itself fails (its `except` falls back to `16`). Linux was accidentally
exempt only because `_detect_hardware()` has no Linux branch at all.

This turned out to already be specified: `tests/test_model_selection_offline.py`
(pre-existing, not written this phase) already speced the exact fix — a
`model_explicitly_set` guard field — as part of a larger, evidently
unfinished feature. That larger feature (`Brain.list_installed_models`,
a runtime "model X" command, Sovereign Mode wiring) is SAM Core
application work and stayed out of scope here. The guard field alone is a
config-layer correctness fix the installer/doctor both depend on, which is
why it's in scope.

**Fix:** `model_explicitly_set: bool = False` added to `Settings`.
`_load_yaml()` sets it when a loaded file carries `primary_model` without
its own persisted `model_explicitly_set` (a hand-written override);
`.save()`-produced files' own persisted value is trusted as-is, so a
previously *auto*-selected model still re-evaluates on the next restart
instead of freezing. `_select_model()` returns immediately if the guard is
set. Three lines changed in `_select_model()`/`_load_yaml()`, one field
added — see `config/settings.py`.

Verified two ways: a new `tests/test_settings_model_guard_offline.py`
(11/11 — both "no override" and "explicit override" cases, plus the
persisted-auto-selection-must-still-re-evaluate edge case), and
independently against `test_model_selection_offline.py`'s own
Settings-scoped assertions (11/11 when run isolated from that file's
unrelated, still-missing `Brain`/`main.py` dependencies).

## Tests added this phase

All four exercise real code paths — real subprocesses, real filesystem
operations, real extracted script text — rather than reimplementing the
logic they're checking:

| File | Checks | What it actually does |
|---|---|---|
| `test_installer_doctor_model_check_offline.py` | 5/5 | Real loopback HTTP server standing in for Ollama, real CLI subprocess |
| `test_installer_venv_idempotency_offline.py` | 10/10 | Extracts the literal venv-reuse lines from `setup.sh`/`setup_linux.sh` and runs real `python3 -m venv` against them |
| `test_installer_data_dirs_offline.py` | 10/10 | Real `config.settings` import per isolated `$HOME`, proves a rerun never touches existing user files |
| `test_settings_model_guard_offline.py` | 11/11 | Real `Settings()` construction against real YAML files, RAM-tier boundaries + explicit-override cases |

## Full regression status

Single clean run, 38 offline test files total: **22 pass, 16 fail**, zero
change in the failing-file list before and after this phase's edits.
Aggregate: 375/378 individual checks across files that report a count.
`compileall` clean repo-wide; `bash -n` clean on both shell installers.

Every one of the 16 failures was checked against `git diff <file>` to
confirm it predates this phase, not assumed from file location alone:

- 6 — missing sandbox dependency (`fastapi`/`pydantic`; no network to
  install them here)
- 6 — the same unfinished M6.2/Sovereign-Mode feature referenced above
  (`sovereign_knowledge_collection`, `sovereign_output_dir`,
  `sovereign_vision_model` don't exist on `Settings`;
  `run_task_with_optional_sovereign_mode` doesn't exist in `main.py`;
  `validate_assistant_name` doesn't exist in `config.settings`)
- 1 — `hands.vision.screen_reader` attribute gap, unrelated file
- 2 — named `_live`, appear to need a running Ollama
- 1 — shares the missing import with its `_live` counterpart

None touch `setup.sh`, `setup_linux.sh`, `setup_windows.ps1`,
`sam_cli.py`, `requirements.txt`, or `config/settings.py`.

## Platform status

| Platform | Status |
|---|---|
| macOS | Idempotency logic implemented, `bash -n` clean, directory-drift/launchd fixes reviewed — network/launchd/Ollama steps themselves not executable in this sandbox |
| Windows | Implemented, **unverified** — no PowerShell interpreter available to even check syntax |
| Linux | Implemented, **unverified** — venv-idempotency logic specifically exercised for real; `apt`/Ollama/model steps not executable here |

No platform is being called "supported" on the strength of code existing.

## Remaining blockers

1. No real-machine run of any of the three installers — the actual
   success criterion for this phase (`README.md` may already claim more;
   if so, that's a documentation gap to close, not a signal this phase is
   done)
2. `setup_windows.ps1` never syntax-checked
3. The 8 pre-existing M6.2/Sovereign-Mode gaps remain — correctly out of
   this phase's scope, not silently ignored
4. `docs/ROADMAP_STATUS.md`'s July 2026 snapshot doesn't reflect this
   phase or the iQOO branch's existence — flagged there, not rewritten
   here (out of scope for a Phase 4 doc to correct other phases' history)

## Exact next action

Real-hardware validation — macOS first (closest to already-verified),
then Linux, then Windows — before any platform status line above can
change from "unverified" to "verified."
