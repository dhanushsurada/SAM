# SAM Desktop — Runtime Bridge Design (Phase B)

Status: design report only. Nothing in this document has been implemented
or run. Written after re-inspecting `runtime/lifecycle/manager.py`,
`runtime/lifecycle/specs.py`, `runtime/health/status.py`,
`core/model_manager.py`, `config/settings.py`, `sam_cli.py`, and `setup.sh`
against the specific questions Phase B raised — not from the Phase A audit
summary alone.

## A. Architecture

```
React (interfaces/desktop)
  |  invoke("runtime_status" | "runtime_start" | "runtime_stop" |
  |         "runtime_restart" | "ollama_status" | "ollama_start" |
  |         "models_list" | "model_select" | "model_pull")
  v
Tauri commands (src-tauri/src/runtime.rs — new)
  |
  +--> CLI/JSON bridge -----------> sam_cli.py --json <subcommand>
  |     (runtime_*, ollama_*)        -> runtime.lifecycle.SAMRuntime
  |     works even when `api`         -> runtime.health.compute_health
  |     is not running yet            -> runtime.ollama.OllamaManager (new)
  |
  +--> HTTP passthrough -----------> GET/POST http://localhost:8420/api/models*
        (models_list, model_select,    -> interfaces/api/server.py
         model_pull)                    -> core.model_manager.ModelManager
        only meaningful once `api`
        is already up
```

Two transports, not two philosophies: everything still terminates in the
existing Python domain objects (`SAMRuntime`, `ModelManager`,
`compute_health`). Which transport a command uses is decided by one
question — **can this operation be meaningful before the `api` process
exists?** Runtime/Ollama status and lifecycle must work when `api` is
down (that's the whole point of them). Model listing/selection/pulling
only mean anything once `api` is already serving `ModelManager` — for
those, going over the gateway's own HTTP API it already has is simpler
than inventing a second channel, and is exactly how `/api/models` and
`/api/models/select` already work today for the browser-only build.

## B. Bridge contract

| Command | Input | Output | Errors | Sync/async |
|---|---|---|---|---|
| `runtime_status` | — | `RuntimeSnapshot` (below) | never fails — a dead process is a *value* in the snapshot, not a thrown error | async, CLI subprocess |
| `runtime_start` | `process?: "voice"\|"api"\|"telegram"` (omit = all) | `{ [name]: OperationResult }` | subprocess/launch failure → `OperationResult.error` | async |
| `runtime_stop` | same | same | same | async |
| `runtime_restart` | same | same | same | async |
| `ollama_status` | — | `OllamaSnapshot` (below) | never fails, same reasoning as `runtime_status` | async, CLI subprocess |
| `ollama_start` | — | `OperationResult` | "already running" is success, not an error; genuine launch failure → `error` | async |
| `models_list` | — | `ModelInventory` (§9) | `OllamaUnavailableError` etc. surfaced as `{code, message}`, not a raw string | async, HTTP GET |
| `model_select` | `name: string` | `OperationResult` | validation failure (incompatible/missing) → `error` with the same message `ModelManager.validate_selection` already produces | async, HTTP POST |
| `model_pull` | `name: string` | `void` (fire-and-forget; result arrives via events) | connection failure → one `model-pull-progress` event with `status: "error"` | async, HTTP POST + SSE relay |

Events (not commands) — the frontend `listen()`s, doesn't `invoke()`:

| Event | Payload | When |
|---|---|---|
| `model-pull-progress` | `{ name, status, digest?, total?, completed?, error? }` — same shape as an Ollama NDJSON line, passed through rather than reshaped | one per line Ollama emits, relayed live |

`name` is validated in Rust against `^[a-zA-Z0-9._-]+(:[a-zA-Z0-9._-]+)?$`
(Ollama's own `name:tag` grammar) **before** it touches a URL or JSON
body — never interpolated into a shell string. Same validation exists
today in `ModelManager.validate_selection`; the Rust-side check is a
second, independent gate at the boundary, not a replacement for it.

### `RuntimeSnapshot` (the one shared shape — see §13)

```json
{
  "processes": {
    "api":      { "state": "READY",   "pid": 4821, "detail": null },
    "voice":    { "state": "STOPPED", "pid": null, "detail": null },
    "telegram": { "state": "STOPPED", "pid": null, "detail": null }
  },
  "ollama": { "state": "READY", "detail": "3 models installed" },
  "brain":  { "state": "READY", "active_model": "qwen2.5:14b" },
  "generated_at": "2026-09-27T12:00:00Z"
}
```

`state` values are `RuntimeStatus` — the existing enum plus one addition
(§D). This is deliberately the *same* object Settings, the Permissions
page, and Onboarding's System-check step all read (§13) — none of them
gets its own query.

## C. State model — three layers, not one enum

| Layer | Owns | Persisted | Who transitions it | React observes via |
|---|---|---|---|---|
| **SetupState** (new) | the onboarding *journey* — `first_run` / `in_progress` / `complete` | `~/.sam_data/setup_state.json` (new, small, separate from `settings.yaml` — this is "have we finished the wizard," not a runtime config value) | the onboarding flow itself, on step completion | read once on app launch (`invoke("setup_state")` — trivial enough not to need its own row in §B) to decide "show onboarding or not" |
| **RuntimeStatus** (existing, extended) | per-process and per-Ollama *liveness* — `STOPPED / STARTING / READY / DEGRADED / FAILED / STOPPING` + new `NOT_INSTALLED` | in-memory + `~/.sam_data/runtime/<name>.json` (existing, for the 3 `SAMRuntime` processes only) | `SAMRuntime` / `OllamaManager`, via `runtime_start`/`stop`/`restart` | polls `runtime_status` (§B) — see below for interval |
| **Model state** | which model is active/selected/installed | `settings.yaml` (`primary_model`, `model_explicitly_set` — existing, unchanged) | `Settings.apply_model_choice()` (existing, unchanged — see §H) | `models_list` on demand, `model-pull-progress` events during a pull |

**Composition, explicitly:** `SetupState` is a coarse switch React checks
once ("am I in the wizard or the app"). Inside either context, the *same*
`RuntimeSnapshot` and model state feed whatever's on screen — Onboarding's
System-check step and Settings' "SAM Runtime" section are two different
**views** over one **model**, never two separate queries that could
disagree.

**Error propagation:** every layer returns a structured
`{ state, detail }` or `{ error: { code, message } }` — never a bare
caught-exception string reaching a component (that's the exact bug
diagnosed last round: `describe()` surfacing a proxy's raw
`statusText`). §13's health unification and this table are the same fix
generalized.

**Polling interval:** `runtime_status` shells out to `sam_cli.py` per
call — cheap, but not free enough for e.g. a 1-second poll. 3–5s while
Onboarding/Settings' runtime section is visible, stop entirely otherwise,
is a reasonable default; the exact number is a tuning detail, not an
architectural one.

## D. Ollama: dedicated manager, not a ProcessSpec — and why

**Decision: a new `runtime/ollama/manager.py::OllamaManager`, not a fourth
`ProcessSpec`.**

`ProcessSpec` and `SAMRuntime`'s stop/PID logic are built on an assumption
that's true for `voice`/`api`/`telegram` and false for Ollama: **SAM is
the sole owner of the process it spawned.** `pid_matches_expected` exists
specifically so SAM never signals a PID it doesn't recognize as its own —
correct and important for SAM's own processes, but Ollama is routinely
already running before SAM ever starts: installed as a Mac menu-bar app, a
`brew services` daemon, or a plain `ollama serve` the user started
themselves in another terminal. Forcing it through `ProcessSpec` would
mean either (a) SAM tries to spawn a second `ollama serve` and race a
port conflict against a perfectly healthy pre-existing instance, or (b)
teaching `SAMRuntime` a "this process may already exist and that's fine,
and I should never try to kill it" exception — at which point it isn't
really the same abstraction anymore.

`OllamaManager` is deliberately narrower than `SAMRuntime`:
- **`status()`** → checks `GET {ollama_host}/api/tags` (the same call
  `ModelManager._fetch_tags` already makes — reused, not re-implemented)
  to decide `READY` (responding) vs `NOT_INSTALLED` (binary not found via
  `shutil.which("ollama")`) vs `STOPPED` (installed, not responding).
- **`start()`** → only meaningful for the `STOPPED` case: spawns
  `ollama serve` (the exact command `setup.sh` already uses) detached, no
  PID tracking beyond "did `/api/tags` start responding within N
  seconds," because SAM has no business claiming ownership of a process
  something else might be managing five minutes from now.
- **No `stop()` at all.** Ollama is a shared local resource other
  applications may depend on; SAM asking to kill it isn't a capability
  the brief asked for, and adding it invites exactly the kind of
  "terminate a process we don't fully own" mistake `pid_matches_expected`
  exists to prevent elsewhere.

`RuntimeStatus` is still reused as the vocabulary (§13's instruction, and
plain consistency) — extended with one new member, `NOT_INSTALLED`,
because "not installed" and "installed but stopped" are different
enough situations (different UI copy, different next action — install
vs. start) that collapsing them into `STOPPED` would be the "generic
message masking three different causes" failure §13 explicitly asks not
to repeat.

## E. Model download

`ModelManager.pull(name: str) -> Iterator[dict]` — a new generator method
on the *existing* class, sitting next to `_fetch_tags`/`_fetch_show`,
using the same `requests` library and the same
`OllamaUnavailableError`-wrapping convention already established there.

**Verified against Ollama's real API, not assumed:** `POST /api/pull`
with `{"model": name}` returns NDJSON by default (`stream` defaults to
true) — a sequence of `{"status": ..., "digest": ..., "total": ...,
"completed": ...}` objects, `completed` absent until a layer actually
starts downloading, ending in a `"success"` status. Mid-pull failures
(unknown model, etc.) arrive as an `"error"` field *inside* the stream,
not as an HTTP error — `pull()` must check for that key on every line
and raise, not just check the HTTP status once at the start.

- **Progress mechanism: streaming, not polling.** Ollama already pushes
  every event; polling would mean either re-deriving progress from
  nothing or Ollama maintaining side-channel state neither the API nor
  this codebase has any other reason to build. `interfaces/api/server.py`
  already has the exact plumbing for "long-lived generator → SSE" (task
  events, `_format_sse`) — a new `POST /api/models/pull` reuses that
  same framing rather than inventing a second streaming convention.
  Rust's `model_pull` command makes that request and re-emits each
  parsed line as a `model-pull-progress` Tauri event.
- **Cancellation: closing the connection, nothing more.** Ollama's own
  docs are explicit that pulls are resumable and share progress across
  calls — so "cancel" is just the client (Rust) dropping the stream;
  FastAPI's generator sees the disconnect (`await request.is_disconnected()`,
  the standard idiom for cancellable SSE in this framework) and stops
  relaying. No separate cancel endpoint, no partial-download bookkeeping
  to invent — Ollama already does that part.
- **Already installed:** `pull()` is never called blindly — the caller
  checks `list_models()` first; if present, the UI shows "Installed,"
  no request is made. (Still safe even if called anyway: Ollama's pull
  is a no-op/near-instant verify against an already-complete model.)
- **Insufficient storage / invalid model / Ollama unavailable:** not
  independently detected — Ollama itself reports these as an in-stream
  `error` (invalid model) or a failed request (Ollama down), and
  `pull()` relays that message rather than SAM trying to pre-compute
  free disk space or validate the model name against a hardcoded list.
  Simpler, and it stays correct as Ollama's own library changes.
- **Persistence:** none needed beyond what Ollama already does on disk —
  there's no partial-download state for SAM to track between app
  restarts.

## F. Onboarding integration

| Step | Today | Becomes | Bridge calls used |
|---|---|---|---|
| Welcome | static copy | unchanged | none |
| System check | pings the iQOO gateway only, explicitly "not required to continue" | real OS/CPU/RAM/storage (already computable — `Settings._detect_hardware()`) + `runtime_status` + `ollama_status` | `runtime_status`, `ollama_status` |
| Model & voice | prints `ollama pull qwen2.5:14b` as copy-paste text | shows the *existing* recommendation (`Settings._select_model()`'s result) with its reasoning (§8), install button if missing | `models_list`, `model_pull` |
| Permissions | static list pointing at System Settings | same content, but reads live state where §13's unified status has it (Notifications, from the existing `/permissions` page's real check) — **OS-level Accessibility/Screen Recording/Mic remain informational**, unchanged; that gap is SAM Core's, not this phase's, and inventing fake status here would be exactly the "fake granted/denied" the brief prohibits | `runtime_status` (for the parts it legitimately covers) |
| Configuration | uses existing Settings mechanisms already | unchanged in write-path; UI may show a summary of what was just configured | none new — still `Settings.apply_model_choice()` |
| Ready | shown unconditionally | gated on `runtime_status` actually reporting `api: READY` (and `ollama: READY` if a local model was selected) — the brief's explicit "do not show Ready until health checks actually pass" | `runtime_status` |

No step is removed. Every "becomes" column reuses a command already
defined in §B — no onboarding-only bridge surface.

## G. Settings integration

New "SAM Runtime" section, reading the *same* `RuntimeSnapshot` and
`ModelInventory` as everything else (§13):

```
SAM Runtime
────────────
Status: Running                    ← derived: all processes/ollama READY
AI Runtime      ✓ Ollama           ← ollama.state
Brain           Qwen 2.5 14B       ← brain.active_model
Services        ✓ API  ✓ Brain     ← processes.api.state, brain.state
                (no separate "Memory" row yet — no runtime signal for it
                 exists anywhere in the audited code; not invented here)
Actions  [Restart SAM] [Check for Problems] [Manage Models] [Change Brain Model]
```

`Restart SAM` → `runtime_restart()` (all processes, no arg). `Check for
Problems` is the GUI face of `sam doctor` — same checks, needs the same
`--json` mode as §B, not a second diagnostic implementation. `Manage
Models`/`Change Brain Model` → `models_list` + `model_select`, i.e. the
`/brain` page's existing selector, reachable from here too rather than
rebuilt.

## H. Security model

- Every Tauri command above is **named and fixed-shape** — no
  `invoke("run_command", {command})` anywhere, matching §11 directly.
- Model identifiers are regex-validated in Rust (§B) *and* still
  independently validated by `ModelManager.validate_selection` in
  Python — the frontend crossing the native boundary doesn't grant it
  a shortcut past checks that already exist.
- The CLI/JSON bridge invokes `sam_cli.py`/`python` with an **argument
  list** (`Command::new("python").arg("sam_cli.py").arg("status").arg("--json")`),
  never a shell string — so there is no injection surface even in
  principle, independent of the regex validation above.
- No new network surface: the HTTP-passthrough commands talk to
  `localhost:8420`, already what the browser build talks to today;
  nothing here opens a port, accepts remote connections, or adds any
  capability SAM didn't already have.
- Conversations, memory, Founder Mode data and prompts are untouched by
  every command in §B — none of them read or transmit anything from
  those subsystems; this is true by construction, not an added
  restriction.

## I. Production gap — explicitly still open

**Good news specific to this phase's design:** `runtime_status`,
`runtime_start/stop/restart`, `ollama_status`, `ollama_start` are CLI-
subprocess-based, not HTTP-based — they do not depend on the Vite proxy
at all and will work unchanged in a packaged `.app`. That part of
production packaging is solved as a side effect of this design, not
deferred.

**Still unresolved, unchanged from last round:** `models_list`,
`model_select`, `model_pull` go over `http://localhost:8420`, reached
today via a *relative* URL that only resolves correctly through Vite's
dev proxy. A packaged `.app` has no such proxy. This phase does not fix
it (§12 says not to unless required) — Phase C or a dedicated
packaging pass will need either an absolute base URL switched on by
`isNative()` (already the exact check `native.ts` uses for other
native/browser branching) plus real CORS on `server.py` (flagged two
rounds ago, still true), or routing those three commands through the
same CLI/JSON bridge as everything else instead of HTTP. Recommend the
former only because `ModelManager` already lives inside the long-running
`api` process and a pull can run for minutes — reusing that process
beats spawning a fresh CLI invocation per model operation.

## J. Files

**New:**
- `runtime/ollama/manager.py` — `OllamaManager` (§D)
- `runtime/health/status.py` — extend `RuntimeStatus` with `NOT_INSTALLED`; extend `compute_health()`'s output to include Ollama (reuse, not a new module)
- `sam_cli.py` — add a `--json` output mode to `status`/`start`/`stop`/`restart`/`doctor` (same commands, second serializer; this *is* the "bridge" §4 asked for)
- `interfaces/api/server.py` — new `POST /api/models/pull` SSE endpoint, thin wrapper over `ModelManager.pull()`
- `src-tauri/src/runtime.rs` — the 9 commands in §B
- `~/.sam_data/setup_state.json` — new persisted file (§C), not a code file but worth naming since nothing writes it today

**Modify:**
- `core/model_manager.py` — add `pull()`
- `interfaces/desktop/src/features/onboarding/OnboardingPage.tsx` — per §F
- `interfaces/desktop/src/features/settings/*` — new "SAM Runtime" section (§G)
- `interfaces/desktop/src/lib/native.ts` — add the 9 command wrappers + the one event listener, same file the notification bridge already lives in

**Explicitly do not touch:**
- `runtime/lifecycle/manager.py`, `specs.py`, `state.py` — reused as-is (§ established architecture); `voice`/`api`/`telegram` specs are unchanged, Ollama is not added as a fourth spec (§D)
- `config/settings.py`'s `_select_model()`/`_detect_hardware()` — reused as-is (§8's instruction); only *exposing* the existing reasoning is new, not the algorithm
- `interfaces/desktop/src/features/permissions/PermissionsPage.tsx` — reads the same `RuntimeSnapshot` once this ships, but its OS-permission (Accessibility/Screen Recording/Mic) rows stay exactly as demo-marked as they are today; that gap belongs to SAM Core, not to this phase
- `interfaces/api/gateway.py`, task system, iQOO, memory, Brain reasoning — untouched; nothing in this design reads or writes any of them

---

Design gate: stopping here, as instructed. Nothing above has been built.
