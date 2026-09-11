# Running SAM Locally — Runtime Guide

Phase 3B, Checkpoint 7. Practical companion to
`docs/architecture/RUNTIME.md`, which explains how the runtime works; this
explains how to use it and what to do when something looks wrong. All
transcripts below are real output from this sandbox during Phase 3B
development, not reconstructed — `sam start`/`stop`/`restart` against the
actual `interfaces/api/server.py`, and a fresh `sam doctor` run.

## Quick start

```
$ python sam_cli.py start api
✅ api: api is ready (pid 511).

$ python sam_cli.py status
── SAM STATUS ──────────────────────────────
❌ Ollama not running → start with: ollama serve
❌ SAM not running → python main.py
✅ Profile at ~/.sam_data

⚠️  api: DEGRADED
❌ telegram: not running → sam start telegram
❌ voice: not running → sam start voice
────────────────────────────────────────────
```

That `DEGRADED` is correct, not a bug in this transcript — this machine had
no Ollama running, so the api process's own health endpoint honestly
reported itself as degraded (`brain_reachable: false`), and `sam status`
just relayed that.

```
$ python sam_cli.py stop api
✅ api: api stopped gracefully (pid 511).

$ python sam_cli.py status
❌ api: not running → sam start api
❌ telegram: not running → sam start telegram
❌ voice: not running → sam start voice
```

`sam start` / `sam stop` / `sam restart` with no name act on all three
processes; give a name (`voice`, `api`, or `telegram`) to target just one.
Restarting genuinely cycles the process — confirmed by pid, not assumed:

```
$ python sam_cli.py start api    # pid 525
$ python sam_cli.py restart api  # pid 533 — different, confirmed dead-then-relaunched
```

## `sam doctor`

```
── SAM DOCTOR ───────────────────────────────
✅ [PASS      ] Python version — 3.12.3
✅ [PASS      ] Configuration loads
✅ [PASS      ] ~/.sam_data writable — /home/you/.sam_data
✅ [PASS      ] fastapi (api process) importable
✅ [PASS      ] uvicorn (api process) importable
✅ [PASS      ] playwright (browser automation) importable
⚠️  [WARN      ] faster-whisper (speech-to-text) importable — not installed — import check only, not a functionality check
⚠️  [WARN      ] python-telegram-bot (telegram bridge) importable — not installed — import check only, not a functionality check
❌ [FAIL      ] Ollama running — not reachable at http://localhost:11434 — start with: ollama serve
✅ [PASS      ] Port 8420 free
✅ [PASS      ] runtime: api — STOPPED (not currently running)
✅ [PASS      ] runtime: telegram — STOPPED (not currently running)
✅ [PASS      ] runtime: voice — STOPPED (not currently running)
⚠️  [WARN      ] Telegram bot token configured — optional — the telegram process won't start without one
❓ [UNVERIFIED] Vision/STT/TTS model files actually downloaded — checked only that the libraries import, not that model weights are present
❓ [UNVERIFIED] OS-level permission grants (mic, camera, accessibility) — not checkable from the CLI

10 pass, 3 warn, 1 fail, 2 unverified (16 checks)
```

Read `FAIL` as "this will stop something from working," `WARN` as "this is
either optional or only partially checked," and `UNVERIFIED` as "this CLI
genuinely cannot check this — you'll have to confirm it yourself." A
`STOPPED` runtime process is `PASS`, not `FAIL` — doctor is asking whether
the environment is *set up correctly*, not whether SAM happens to be running
right now.

### New in Phase 4: configured-model check

`sam doctor` used to stop at "Ollama running" — confirming *some* model was
pulled, but not the one SAM is actually configured to use. It now checks
`settings.primary_model` against the same `/api/tags` response, no extra
request. Real transcript, this sandbox, Ollama not running (a genuinely
common state — the case this addition is most likely to actually matter for
first-run, before anyone's started Ollama yet):

```
❌ [FAIL      ] Ollama running — not reachable at http://localhost:11434 — start with: ollama serve
❓ [UNVERIFIED] Configured model pulled — Ollama unreachable — could not check
```

With Ollama reachable, this becomes one of:

```
✅ [PASS      ] Configured model 'qwen2.5:14b' pulled
```
```
❌ [FAIL      ] Configured model 'qwen2.5:14b' pulled — not found among pulled models — run: ollama pull qwen2.5:14b
```

## Where things live

- `~/.sam_data/runtime/<name>.json` — one state file per managed process
  (`pid`, `command`, `started_at`, `phase`, `message`). Safe to delete by
  hand if you're sure the process is actually gone; `sam start` will treat
  a genuinely-dead pid the same way regardless.
- `~/.sam_data/iqoo/tasks.db`, `~/.sam_data/ecosystem/devices.db` —
  unchanged by Phase 3B, still where they were.
- Everything persistent lives under `~/.sam_data/` — `memory/chroma/`,
  `founder_mode/` (+ `export/`), `skills/compiled/`, `logs/`. **Phase 4
  fix:** `setup.sh` used to also create a second, dead set of these same
  directories relative to the repo itself (`./logs/`, `./memory/store/`,
  etc.) — leftover from before the `~/.sam_data` migration, never actually
  read by `memory/store.py`, `founder_mode/manager.py`, or
  `skills/compiler.py` (all three already pointed at `~/.sam_data`; see
  `skills/compiler.py`'s docstring for that migration's own history). The
  installer now creates only the real ones. If you have an old
  installation with both sets on disk, the repo-relative ones are safe to
  delete — nothing reads them — but the installer won't touch them for you
  either way.

## Installing / reinstalling SAM (Phase 4)

Three installers, one shared structure: check platform → Python →
PortAudio → Ollama → RAM-tiered model pull → venv → `pip install` →
Playwright Chromium → initialize `~/.sam_data`.

- **`setup.sh` (macOS).** Safe to run again on an existing install: reuses
  a valid `.venv` instead of recreating it (checks for `.venv/bin/python3`;
  if `.venv` exists but looks incomplete, it's rebuilt, not silently left
  broken); `ollama pull` is already idempotent server-side; the `launchd`
  agent is unloaded before its plist is replaced if one's already running,
  then reloaded, with the real `launchctl` exit code checked — the old
  behavior silently swallowed load failures. Never touches an existing
  `~/.sam_data` or your `settings.yaml`.
- **`setup_windows.ps1` (Windows).** Same `.venv` reuse pattern, same
  `~/.sam_data` target. The Task Scheduler step already used
  `-Force`, which safely replaces an existing task — no separate
  unload step needed there, unlike launchd. **Implemented, not verified
  on real Windows hardware** — no environment to test it against so far.
- **`setup_linux.sh` (Linux, new in Phase 4).** Debian/Ubuntu (`apt`)
  only — checks for `apt` explicitly and exits cleanly elsewhere rather
  than guessing. `portaudio19-dev` via `apt`, Ollama via its official Linux
  install script, RAM read from `/proc/meminfo`. Same venv-reuse and
  `~/.sam_data` behavior as macOS. **No auto-start-on-boot in this first
  version** — no systemd unit yet, start manually. **Implemented, not
  verified on real Linux hardware.**

None of the three will silently pull large models without printing what
it's doing first, and none will delete or overwrite `~/.sam_data` or an
existing `settings.yaml` on a rerun.

## Troubleshooting

**`sam status` shows FAILED for a process.** Check the message inline —
`sam status` prints the actual failure reason for a `FAILED` process, not
just the label. It persists until you try `sam start <name>` again; it
won't silently clear itself.

**"Port 8420 free" says WARN, or `sam doctor` shows the api process as
something other than SAM.** Something other than SAM's own api process is
bound to that port. `runtime` will not touch it — starting `api` while
something else holds the port will surface as a startup failure with the
process's own output, not a silent hang.

**`sam status` claims SAM is running when you know it isn't (or the
reverse).** ~~That's the *existing*, pre-Phase-3B `SAM running (PID: ...)`
line specifically — it uses `pgrep -f main.py`, a loose substring match
against every process's full command line~~ **Fixed since this doc was
written.** `cmd_status` now checks the same PID-matched state-file path the
`voice`/`api`/`telegram` lines below it already used, and only falls back
to the old loose `pgrep -f main.py` match if SAM was started manually
outside `sam start` (no state file to check) — and that fallback line is
now honestly labeled "best-effort match — not started via `sam start`"
rather than shown with the same confidence as a verified match. See
`sam_cli.py::cmd_status` and the code comment there for the fix history.

**`sam logs` shows nothing even though SAM has clearly been running.**
~~Also pre-existing, also unrelated to Phase 3B: `main.py` writes its log
to `./logs/sam.log`... while `sam logs` reads `~/.sam_data/logs/sam.log` —
two different files~~ **Fixed since this doc was written.** `main.py` now
writes its log to `~/.sam_data/logs/sam.log`, the same path `sam logs`
reads. See `main.py`'s logging setup and the code comment there for the
fix history.

**Telegram or voice won't start under `runtime`.** The mechanism itself
(spawn, track, signal, reap) is the same code path proven against the real
api process above and against throwaway dummy processes in
`tests/test_runtime_lifecycle_offline.py` — but the real `main.py` and
`telegram_bridge.py` processes themselves were never started through
`runtime` end-to-end during this phase (no microphone / no Telegram token
in the development sandbox). If `sam start voice` or `sam start telegram`
fails, `sam status`/the printed message will show real captured output from
the process itself — read that first; it's the process failing, not a
mystery in the runtime layer.

**On Windows.** `sam stop`/`sam restart` use `tasklist`/`taskkill` rather
than POSIX signals, following the same platform-branch pattern
`config/settings.py` already uses for hardware detection. This has never
run on an actual Windows machine — only implemented by pattern-matching an
existing convention. Treat it as unverified until someone tries it there.

**I set `primary_model` in `~/.sam_data/settings.yaml`, but SAM keeps
using a different model after restart.** ~~`_select_model()` unconditionally
overwrote `primary_model` with a RAM-tier default every startup, regardless
of what settings.yaml said — YAML's value survived for one line of
`__post_init__` before being silently clobbered~~ **Fixed since this doc
was written.** A `model_explicitly_set` flag now guards that: set the first
time `primary_model` appears in your config, checked by `_select_model()`
before it does any RAM-tier auto-selection. `sam doctor`'s configured-model
check (above) will tell you which model is actually in effect either way.
