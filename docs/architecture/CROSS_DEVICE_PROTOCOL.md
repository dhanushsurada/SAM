# SAM Connect — Cross-Device Protocol

agent/cross-device (Agent 3). Covers `connect/` (core, transports, services)
and the `/api/connect/*` HTTP surface `interfaces/api/connect_routes.py`
wires it into — the device pairing, trust, capability, transport, task
routing and context-handoff layer the Master PDR section 16 calls out as
Agent 3's shared integration contracts.

Does not touch or supersede `docs/iqoo/PROTOCOL.md` (the `/api/iqoo/*`
phone-task contract) or `docs/PHASE_2_TELEGRAM_BRIDGE.md` — see §1 for how
this relates to both.

---

## 1. Scope and boundary

SAM Connect answers three questions the rest of SAM doesn't: **who** is this
device, **what** can it do, and **is it here right now**. It does not
execute AI tasks itself (that's SAM Core's Brain/Planner/ReactLoop) and it
is not a second memory system — `context_ref`/`handoff_state` (§9) are
opaque pointers it carries on Core's behalf, never a copy of Core's own
session state.

```
connect/
├── core/
│   ├── device_registry.py   Identity, pairing, trust, capabilities, connection state
│   ├── capabilities.py      The capability vocabulary + validation
│   ├── crypto.py            Ed25519 primitives (generate/serialize/sign/verify)
│   └── events.py            ConnectEventBus — device.*/task.*/voice.* streams
├── transports/
│   └── lan_http.py          Same-WiFi HTTP: request signing, replay protection, pairing payload
├── bridges/
│   └── vivo_iqoo/           Documentation only — no vendor SDK integration exists (§11)
└── services/
    └── task_handoff.py      DeviceTaskRouter — routing, lifecycle, idempotency, handoff

interfaces/api/
├── device_auth.py           FastAPI dependency wrapping lan_http.verify_request
├── connect_schemas.py       Pydantic request/response models for the below
└── connect_routes.py        The actual /api/connect/* FastAPI router
```

### Relationship to `/api/iqoo/*`

Two directions exist, and they use two different, already-separately-solved
paths rather than one endpoint with a mode flag:

- **Android → Desktop/Core** (phone submits an instruction for Core's Brain
  to execute): the existing `/api/iqoo/tasks` (`docs/iqoo/PROTOCOL.md`).
  Unchanged by this branch — see below for why.
- **Desktop → Android** (Core/desktop routes a task to the phone's *own*
  capabilities — "open Instagram on my phone"): new, `/api/connect/tasks`
  (§8).

`/api/iqoo/tasks` today has **no device trust check at all** — confirmed by
reading `interfaces/api/server.py`/`gateway.py` for this branch: any HTTP
client that can reach the port can submit a task. Wiring `require_trusted_device`
onto it was deliberately **not** done in this phase: that route already has
a real consumer (`interfaces/desktop/src/api/client.ts`) and a real,
passing offline test suite (`tests/test_iqoo_phase1/2/3a_offline.py`) that
assume no auth header, and hard-requiring one would be a breaking change to
a surface Agent 3 doesn't own (`interfaces/api/gateway.py`/`task_store.py`
are SAM Core's, not Connect's — see §13's Non-Goals). **Recommended
follow-up for Agent 4**: decide whether `/api/iqoo/tasks` should require
device auth going forward, and if so, coordinate the breaking change with
whatever already depends on the current open-access contract.

---

## 2. Device model & identity

One `devices` table (`connect/core/device_registry.py`, additive migration
onto the pre-existing Phase 2 schema — see that file's own comments for the
column-by-column history):

| Column | Meaning |
|---|---|
| `channel` | `"telegram"` or `"direct"` (LAN/WiFi-paired — `DIRECT_CHANNEL`) |
| `external_id` | Telegram chat_id, or a client-generated UUID for `"direct"` |
| `device_name` | Display name |
| `status` | `pending` → `awaiting_redemption` → `trusted` → `revoked` |
| `platform` | `"android"` etc. (`"direct"` only) |
| `protocol_version` | This document's version, currently `"1.0"` |
| `capabilities` | JSON, §5 shape (`"direct"` only) |
| `public_key` | Ed25519 public key, PEM (`"direct"` only) |
| `connection_state` | `online`/`offline`, heartbeat-driven (`"direct"` only — see below) |
| `paired_at`, `last_active` | Timestamps |

`(channel, external_id)` is the real identity key — `revoke()`/`rename()`
are keyed by the internal integer `id` instead (a desktop management UI
always has it from `list_devices()`; a device only ever knows its own
`external_id`). `connection_state` reads back as `"n/a"` for any channel
other than `"direct"` (`connection_state_for()`) — a Telegram device is
authenticated per-message by Telegram itself and never heartbeats, so
`"offline"` would be actively misleading.

---

## 3. Pairing & trust

One-time token, same shape as the existing Telegram flow
(`interfaces/telegram/pair_new_device.py`) generalized to a second channel:

```
Desktop                                  Phone
   │  create_pairing_token("direct")        │
   │  → show QR (build_pairing_qr_payload)  │
   │─────────────────────────────────────►  │  scans QR
   │                                         │  generates its own Ed25519 keypair
   │                                         │  POST /api/connect/pairing/redeem
   │  ◄─────────────────────────────────────│  {token, device_id, device_name,
   │                                         │   platform, public_key, capabilities}
   │  validate token, store public_key       │
   │  status → trusted                       │
   │─────────────────────────────────────►  │  {"device_id": ..., "status": "trusted"}
```

QR payload (`POST /api/connect/pairing/start` → `PairingStartResponse`):

```json
{"v": "1.0", "token": "…", "host": "192.168.1.42", "port": 8420, "expires_at": "…"}
```

`host` is best-effort LAN IP detection (`lan_http.detect_lan_ip()` — the
no-packets-sent UDP-connect trick); falls back to `127.0.0.1` if no network
interface is found. Token TTL: `PAIRING_TOKEN_TTL_MINUTES` = 10, one-time
use, deleted on redemption or expiry.

**Trust bootstrap, explicitly**: the pairing token proves "this device saw
the QR code on the trusted screen." SAM never possesses the device's
private key — only the public half ever crosses the network — so a leaked
DB backup can't be used to impersonate a paired device (see
`connect/transports/lan_http.py`'s module docstring for the full reasoning,
and `licensing/keygen.py` for the same Ed25519 pattern applied to license
signing instead of devices).

**Revocation and re-pairing**: `POST /api/connect/devices/{id}/revoke`
sets `status = revoked` and immediately fails auth on that device's next
signed request (`DeviceNotTrustedError` → 401) — confirmed by
`tests/test_connect_offline.py`'s revocation-then-signed-request check. A
revoked device **can** be re-paired later through the same one-time-token
flow above; that's a deliberate design choice, not a gap — a fresh token
requires the same physical access to the trusted screen as any first-time
pairing. (A real bug in the original re-pairing logic — a revoked row's
`(channel, external_id)` slot wasn't visible to the "does this row already
exist" check, so re-pairing crashed with a SQLite `IntegrityError` instead
of ever completing — was found and fixed while writing this branch's test
suite; see `connect/core/device_registry.py`'s `redeem_token` comments.)

---

## 4. Request signing (transport authentication)

Full scheme: `connect/transports/lan_http.py`'s module docstring (canonical
reference — not duplicated field-by-field here to avoid the two drifting
apart). Summary: four headers —

```
X-SAM-Device-Id:  <device_id>
X-SAM-Timestamp:  <unix seconds>
X-SAM-Nonce:      <>=16 random url-safe chars>
X-SAM-Signature:  <base64 Ed25519 signature over METHOD\nPATH\nTIMESTAMP\nNONCE\nSHA256(BODY)>
```

Rejected (all → `DeviceAuthError` subclass → HTTP 401) for: missing any
header, a timestamp more than 120s from server time, a `(device_id, nonce)`
pair already seen within that window (replay), a device that was never
paired or is revoked, a corrupt stored key, or a signature that doesn't
verify. Every *successful* verification records a heartbeat as a side
effect (`DeviceRegistry.record_heartbeat`) — there is no separate
"authenticate" step before "heartbeat"; any signed request IS the
heartbeat. `POST /devices/{id}/heartbeat` (§6) exists anyway because it
also returns queued tasks (§9), not because signing alone doesn't count as
liveness.

**Order of checks, and why it matters** (`lan_http.verify_request`):
headers present → timestamp within ±120s → signature decodes → device is
trusted and its stored key loads → **signature verifies** → **only then**
`(device_id, nonce)` is recorded (an atomic check-and-record under the
cache's lock, so two concurrent copies of one valid request still yield
exactly one success) → heartbeat recorded. The nonce used to be recorded
*before* the signature check; that let anyone on the LAN grow the cache
with garbage and, worse, burn a legitimate request's nonce by submitting a
forged copy of it first (the genuine request then read as a replay).
Unauthenticated input now cannot mutate replay state at all — covered by
`test_failed_auth_does_not_touch_nonce_cache`.

**Nonce lifetime is 2× the timestamp window (240s), not 1×.** A timestamp
is accepted anywhere in [now−120s, now+120s], so a request from a device
whose clock runs ahead is accepted at t0 with ts up to t0+120s and stays
timestamp-valid until t0+240s. A 120s nonce memory left a real replay gap
in (t0+120s, t0+240s]. Found by a regression test that failed against the
original 1× TTL (`test_nonce_cache_and_replay_window`), then fixed.

**Known limitation**: the nonce cache is in-memory/per-process
(`lan_http.NonceCache`). Fine for today's single-process
`uvicorn.run(app, ...)` (`interfaces/api/server.py`); flagged for whoever
ever runs this as more than one process. A server restart also forgets
recent nonces, so a captured request whose timestamp is still in-window
can be replayed once after a restart.

---

## 5. Capability model

`connect/core/capabilities.py`. Closed vocabulary, not free-form strings:

```
voice | notifications | app-launch | camera | device-control
```

Each reported as `{"available": bool, "permission": "granted"|"denied"|"not_requested"}`.
`available=false` always forces `permission` back to `not_requested` server-side
(can't be simultaneously "doesn't exist" and "granted"). A device only
needs to report what it actually has — an omitted key means unavailable.
`device_supports(capabilities, name)` — used by task routing (§8) — is
`True` only for `available=true AND permission="granted"`; unknown, missing,
unavailable, and available-but-ungranted are all `False` (routing surfaces
*why* separately via `CapabilityUnavailableError`, not a bare denial).

Reported at pairing time, updatable via `PUT /api/connect/devices/{device_id}/capabilities`
(device-authenticated, ownership-checked — a device can only update its
own).

---

## 6. REST endpoints

All under `/api/connect`. "Auth" = `require_trusted_device`
(`interfaces/api/device_auth.py`) — the caller must be the signed-in
device itself, checked against the path's `device_id` where both appear.
"local" = `require_local_caller` (`interfaces/api/connect_routes.py`,
added on this branch's hardening pass) — restricted to the loopback
interface via `ipaddress.ip_address(...).is_loopback` (checked against the
whole `127.0.0.0/8` range and IPv6 `::1`, plus the IPv4-mapped-IPv6 form
`::ffff:127.0.0.1` a dual-stack socket can legitimately present — a
hardcoded `{"127.0.0.1", "::1"}` string check, this function's first
version, silently rejects both of the latter two), since these are
desktop/Core-only by design; see §12 for why this is safe to enforce (the
real desktop client only ever calls this API same-origin). Endpoints with
neither are device-facing and reachable over the LAN as designed
(`/pairing/redeem`, capabilities, heartbeat, every task-lifecycle call a
device itself makes).

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/pairing/start` | local | §3 |
| POST | `/pairing/redeem` | — | §3. 422 malformed key/capabilities, 401 bad/expired/reused token |
| GET | `/devices` | local | `?include_pending=true` to see mid-pairing/revoked rows too |
| POST | `/devices/{id}/revoke` | local | `{id}` = internal int, from `/devices` |
| POST | `/devices/{id}/rename` | local | `{"name": "..."}` |
| PUT | `/devices/{device_id}/capabilities` | device | `{device_id}` = external_id; 403 if it doesn't match the caller |
| POST | `/devices/{device_id}/heartbeat` | device | Returns `connection_state` + full pending-task snapshot (§9) |
| POST | `/tasks` | local | Desktop/Core → device. 404 unknown device, 422 missing capability |
| GET | `/tasks/{task_id}` | — | 404 if unknown |
| POST | `/tasks/{task_id}/ack` | device | 403 wrong device, 409 already terminal |
| POST | `/tasks/{task_id}/progress` | device | `{"message": "...", "pct": 0-100}` |
| POST | `/tasks/{task_id}/action` | device | `{"description": "..."}` |
| POST | `/tasks/{task_id}/verification` | device | `{"verified": bool, "detail": "..."}` — signal only, doesn't complete/fail |
| POST | `/tasks/{task_id}/complete` | device | `{"result": {...}}` |
| POST | `/tasks/{task_id}/fail` | device | `{"error": "..."}` |
| POST | `/tasks/{task_id}/cancel` | local | Returns `{"cancelled": false}` (not an error) if already terminal |
| POST | `/tasks/{task_id}/handoff` | local | §10. `{"new_target_device_id": "...", "reason": "..."}` |
| GET | `/events?stream=<name>` | — | SSE, §7 |

### Error → status mapping

`connect/services/task_handoff.py`'s `TaskRoutingError` hierarchy, mapped
by `interfaces/api/connect_routes.py`'s `_raise_for_task_error`:

| Exception | HTTP |
|---|---|
| `UnknownDeviceError` | 404 |
| `TaskNotFoundError` | 404 |
| `CapabilityUnavailableError` | 422 |
| `TaskNotOwnedByDeviceError` | 403 |
| `InvalidTaskStateError` | 409 |
| `DeviceAuthError` (any subclass, from `require_trusted_device`) | 401 |
| `CapabilityValidationError` (malformed capability map) | 422 |
| `ValueError` from `redeem_pairing` (malformed key/capabilities) | 422 |
| non-loopback caller on a `local`-only route | 403 |

---

## 7. Event model

`connect/core/events.py`. Vocabulary (Master PDR §16 / Agent 3 prompt §7):

```
device.connected  device.disconnected  device.updated
task.created  task.started  task.progress  task.action
task.verification  task.completed  task.failed  task.cancelled
voice.started  voice.stopped
```

(`task.cancelled` is one addition beyond the prompt's literal list — every
other terminal task outcome has its own event, so cancellation needs one
too. Documented, not snuck in.)

**Streams** (`GET /api/connect/events?stream=<name>`, SSE,
`Last-Event-ID`-reconnect-safe, identical framing to
`GET /api/iqoo/tasks/{id}/events`):

```
device                    every device.* event, all devices — the Devices page's live view
device:<external_id>      device.* events for one device
task:<task_id>            every event for one routed task — terminates the stream on task.completed/failed/cancelled
voice                     every voice.* event
```

A task event is published to **both** `task:<id>` and `device:<target>` —
watching one device's stream shows every task routed to it inline with its
connect/disconnect history.

**`device.connected`/`device.disconnected` are not published by
`lan_http.py` or `task_handoff.py`** (deliberately — neither module has an
event-bus dependency; see their docstrings). `device_auth.py`'s
`require_trusted_device` publishes `device.connected` on an
offline→online transition (not on every heartbeat from an
already-online device); the background sweep in `connect_routes.py`
(§9) publishes `device.disconnected` on the reverse transition.
`device.updated` covers pairing, rename, revoke, and capability changes.

**voice.started/voice.stopped are defined but not yet published by
anything** — reserved for whichever future work wires SAM's voice
pipeline into a cross-device stream. Not a gap in this branch's scope;
nothing in the Agent 3 prompt asked for a voice *producer*, only the event
names to exist.

---

## 8. Device task lifecycle

`connect/services/task_handoff.py`. **Not** `interfaces/api/task_store.py`
and does not replace it — that's Core's own record of instructions the
phone sends *it* to execute (Brain → ReactLoop). A `DeviceTask` is routed
*to* a device for *that device* to execute with its own capabilities.

```
created → dispatched ──────────────► started → in_progress → completed
              │                                             → failed
              └─► queued_offline ─► (redelivered on         → cancelled
                   (device offline    reconnect, §9)         → timed_out
                    at dispatch)
```

- `created`: capability pre-checked (§5) before the row even exists — a
  request for a capability the device hasn't reported as available+granted
  never creates a task at all.
- `dispatched` vs `queued_offline`: decided by the target's
  `connection_state` at create time.
- `started`: the device itself called `ack()` — proof of receipt, not just
  proof SAM attempted delivery.
- `completed`/`failed`/`cancelled`/`timed_out`: terminal — the event
  stream stops accepting further events for that task (§7), and every
  device-reported call (`ack`/`progress`/`action`/`verification`/
  `complete`/`fail`) rejects a task already in one of these four
  (`InvalidTaskStateError` → 409), confirmed for every terminal→X
  transition by `tests/test_connect_offline.py`'s
  `test_state_machine_transitions`.

**Finding (verified behavior, not a defect this branch changed)**: the
diagram above reads as a strict progression, but the actual guard is only
"not already terminal" — `complete()`/`fail()`/`progress()`/`action()`/
`verification()` are all callable directly from `dispatched` or
`queued_offline`, skipping `ack()`/`started`/`in_progress` entirely. A
device that finishes something instantly has no obligation to round-trip
through `ack()` first. Ownership (`_check_ownership`) still gates every
call — only the actual target device can report against its own task — so
this is looseness in the diagrammed sequencing, not a trust gap. Left
as-is rather than tightened: this file predates this branch's hardening
pass and tightening it wasn't a "concrete implementation defect," just a
looser-than-diagrammed guard.

---

## 9. Offline, reconnect, timeouts, duplicates

- **Offline at dispatch**: task sits `queued_offline`. The device's *next*
  successful heartbeat (`POST /devices/{id}/heartbeat`, which is itself
  just "a successfully signed request" — §4) calls
  `get_pending_for_device()`. **This returns every task currently in
  `dispatched` OR `queued_offline` for that device, not just ones newly
  redelivered this call** — a `queued_offline` task flips to `dispatched`
  as a side effect and is included, but a task *already* `dispatched`
  (sent before, not yet acked) is included too. Safe to call on every
  heartbeat: a device that already knows about an outstanding task just
  sees it again until it `ack()`s (which moves it to `started` and drops
  it from the set) — verified by `tests/test_connect_offline.py`'s
  `test_offline_reconnect_cycles`, including across three separate
  offline/online cycles.
- **Disconnect detection**: a background thread in
  `interfaces/api/connect_routes.py` (`start_background_tasks()`, called
  from `server.py`'s existing startup hook) calls `sweep_offline()` and
  `sweep_timeouts()` every 30s. `sweep_offline(stale_after_seconds=90)`
  flips any `"direct"` device with no heartbeat in 90s to `offline` and
  publishes `device.disconnected` for each transition (not every tick —
  only the transition).
- **Task timeout**: `sweep_timeouts()` fails out (`status = timed_out`) any
  non-terminal task whose `updated_at` is older than its own
  `timeout_seconds` (default 300; pass a longer one to `create()` for a
  known-slow action).
- **Duplicate requests / idempotency**: `create()` takes an optional
  `idempotency_key`. A second `create()` for the same
  `(target_device_id, idempotency_key)` returns the *original* task
  instead of creating another — a flaky LAN connection retrying a POST is
  safe, including genuinely concurrent retries (not just one after the
  other): a partial `UNIQUE(target_device_id, idempotency_key)` index
  (`WHERE idempotency_key IS NOT NULL`) enforces this at the database
  level, with `create()` catching the resulting `IntegrityError` on the
  losing side of a race and returning the winner's already-committed task
  instead. This replaced a check-then-insert pattern that was not
  actually atomic — found as a genuine, intermittent (not deterministic)
  failure under a real 10-thread concurrent-`create()` test with a
  shared `threading.Barrier`, not a theoretical concern. See
  `tests/test_connect_offline.py`'s `test_concurrency` (also covers 10
  threads racing to redeem the same one-time pairing token: exactly one
  succeeds, confirmed safe by SQLite's own write-serialization — no fix
  needed there, since that path's "check" and "act" are the same atomic
  `UPDATE ... WHERE status = 'awaiting_redemption'`).
- **Reconnecting after a lost connection generally**: this protocol is
  request/response + SSE, not a persistent socket — there is no
  server-observable "reconnecting" state. A client's own UI may show one
  locally while its retry loop runs; the server only ever reports
  `online`/`offline`.

---

## 10. Context handoff

`DeviceTaskRouter.handoff(task_id, new_target_device_id, reason=...)`.
Moves a task's *thread* to a different device without losing identity:
creates a **new** `DeviceTask` (`handoff_of` = the original `task_id`,
same convention as `task_store.py`'s `retried_from`), copies `context_ref`
and `handoff_state` across **unchanged** — this module never inspects or
interprets either, only relays them — and cancels the original if it
wasn't already terminal. The original `task_id`'s full event history stays
exactly where it is, still fetchable via `GET /tasks/{original_id}`: "a
task should not become a completely separate task merely because the user
changes devices" (Agent 3 prompt §8) is satisfied by a real, traceable
link, not by pretending it's the same `task_id`.

`context_ref`/`handoff_state` are **opaque** — SAM Core assigns and
interprets them (e.g. a conversation/session id, a snapshot of where a
multi-turn exchange left off); Connect only carries them. This is the
concrete form of "do not build a second memory system — SAM Core remains
the source of truth" (Agent 3 prompt's own guardrail).

**Finding (verified behavior)**: handing off an already-terminal task
(completed/failed/cancelled/timed_out) **succeeds** rather than rejecting
— the guard is `if original.status not in TERMINAL_STATUSES: cancel it`,
a conditional on whether there's anything left to cancel, not a gate on
whether handoff is allowed. The terminal original is left exactly as it
was (still queryable, unmodified) and a new linked task is still created.
Read generously, this is a feature: "continue this conversation on my
desktop, the quick phone task already finished" is a legitimate handoff
even though the phone-side task's own outcome is done. Not tightened for
the same reason as §8's finding — no concrete defect requires it.

---

## 11. `connect/bridges/vivo_iqoo/`

Documentation only (`README.md`) — no real vivo/iQOO vendor SDK
integration exists anywhere in this codebase (confirmed by this branch's
own repository audit, consistent with `docs/iqoo/PHASE_3A5_MIGRATION.md`'s
identical finding). Today's "phone connectivity" is the generic same-WiFi
HTTP transport this document describes (§4), not an Office Kit/vendor
integration. Left as a reserved package for a real future vendor bridge,
not populated further by this branch.

---

## 12. Known limitations / explicitly deferred

- **No real Android device or real Mac validated this branch.** Everything
  in §2–§10 is verified by `tests/test_connect_offline.py` (138/138
  checks — the original 77 plus an adversarial-hardening pass covering
  15 signature-tampering cases, extra pairing-security cases, explicit
  state-machine transitions, multi-hop handoff, event-stream isolation,
  and repeated offline/reconnect cycles — real SQLite, real Ed25519
  signatures, no mocks) against a hand-written reference client — not
  against a physical phone. §14 is the acceptance-test specification for
  when one is available. This is the Agent 3 prompt's own stop condition
  ("Android capabilities are not defined sufficiently to create a
  reliable contract") in a softer form: the *contract* is fully defined,
  self-consistent, and adversarially tested, but nothing has
  round-tripped through a real device yet.
- `tests/test_connect_api_offline.py` (the FastAPI/HTTP-layer test file)
  and `tests/test_architecture_boundaries_offline.py` could not be
  executed in this branch's sandbox on either development pass — no
  network access to install `fastapi`/`pydantic`/`uvicorn`/`httpx`
  (confirmed directly via `pip install`/`pip download`, not assumed).
  Run them for real before merging.
- `/pairing/start` and the other desktop-only `/api/connect/*` routes
  (§6's "local" column) are restricted to loopback callers as of this
  branch's hardening pass — closing what was, on the first pass, an open
  known limitation. `/pairing/redeem` and every device-facing route are
  deliberately still open on the LAN (that's the point — a device isn't
  loopback).
- `/api/iqoo/tasks*` still has no device trust check at all (§1,
  deliberately unchanged this phase — flagged for Agent 4).
- Nonce replay protection (`lan_http.NonceCache`) is in-memory and
  per-process (§4): a plain dict guarded by a `threading.Lock`, no
  persistence, no cross-process sharing. **Correction to an earlier
  revision of this document**, which said it was "pruned lazily on each
  check" and "confirmed by reading it" — that repeated the class's own
  docstring rather than the code. The code drops expired entries in bulk
  only when the dict exceeds 4096 entries; below that, expired entries
  linger in memory but are ignored on lookup. Because only
  signature-verified requests are recorded (§4), growth is bounded by what
  authenticated devices send within one 240s TTL; a sustained burst past
  ~17 requests/second from one device keeps the live set above the
  threshold and makes every check rebuild the dict under the lock —
  wasteful, not incorrect. Correct and sufficient for today's single
  `uvicorn.run(app, ...)` process (`interfaces/api/server.py`). **Future
  requirement, not addressed here**: if SAM Connect ever runs as more
  than one process (multiple workers, a process-per-request model, etc.),
  replay protection needs a shared store (e.g. Redis, or the existing
  SQLite DB with a `UNIQUE(device_id, nonce)` table and a cleanup sweep)
  — deliberately not built now, since nothing in this codebase runs
  multi-process today and adding an external dependency for a
  not-yet-real deployment shape isn't justified.
- **Transport is plain HTTP, not TLS.** Requests are signed, not
  encrypted: an on-path observer on the LAN can read task payloads and
  results (they are authenticated and replay-protected, not
  confidential). The pairing QR carries a one-time token, never a
  long-lived credential, but `/pairing/redeem`'s body (public key,
  capabilities) also crosses the LAN in the clear. Acceptable for a
  same-WiFi hackathon-scale product; a hard requirement to revisit before
  anything sensitive is routed through Connect.
- `voice.started`/`voice.stopped` are defined, nothing publishes them yet (§7).
- No Bluetooth/SAM Direct transport — same-WiFi HTTP only (§11).
- `connection_state` for a `"direct"` device is heartbeat-inferred, not a
  push notification of disconnect — up to `HEARTBEAT_STALE_SECONDS` (90s)
  + the sweep interval (30s) of lag before `device.disconnected` fires.

---

## 13. Contract requirements for Agents 1 (Desktop) & 2 (Android)

**For Agent 2 (Android)**: implement the device side of §3 (generate an
Ed25519 keypair on first launch via any Ed25519 library, persist the
private key locally, never transmit it), §4 (sign every `/api/connect/*`
request with the four headers), report real capabilities (§5) matching
what OS permissions are actually granted, call
`POST /devices/{id}/heartbeat` periodically (a reasonable interval is well
under `HEARTBEAT_STALE_SECONDS` — every 30-60s is safe) and execute
whatever `pending_tasks` it returns, reporting back via `ack` →
`progress`/`action`/`verification` (optional, as many as apply) →
`complete`/`fail`.

**For Agent 1 (Desktop)**: render the pairing QR from
`POST /pairing/start`'s response, a Devices management view from
`GET /devices` (revoke/rename), and — for any "do X on my phone" feature —
`POST /tasks` with a `required_capability` and a live view via
`GET /events?stream=device:<id>` or `task:<task_id>`.

**Non-Goals restated** (Branch Discipline, Agent 3 prompt §15): this
branch does not implement desktop UI, Android UI, or rewrite SAM Core.
`interfaces/api/gateway.py`, `task_store.py`, `schemas.py`, and
`server.py`'s existing `/api/iqoo/*` routes are untouched except for the
three-line addition documented in §1 and this file's own git history.

---

## 14. Real-device acceptance test specification

Not implemented here (no Android/Desktop UI in this branch's scope) — the
sequence Agents 1/2's real integration should exercise once both exist,
in order:

```
1.  Mac/SAM:    POST /api/connect/pairing/start           -> {token, host, port}
2.  Desktop UI: render {host, port, token} as a QR code
3.  Android:    scan QR, generate an Ed25519 keypair locally
4.  Android:    POST /api/connect/pairing/redeem
                  {token, device_id, device_name, platform,
                   public_key, capabilities}               -> {status: "trusted"}
5.  Android:    sign and send a request (any — heartbeat is simplest)
6.  Mac/SAM:    GET /api/connect/events?stream=device       -> sees device.connected
7.  Desktop UI: GET /api/connect/devices                    -> phone listed, online
8.  Desktop UI: POST /api/connect/tasks
                  {target_device_id, action, required_capability} -> 201, dispatched
9.  Android:    POST /devices/{id}/heartbeat                -> pending_tasks: [the task]
10. Android:    POST /tasks/{id}/ack                        -> started
11. Android:    POST /tasks/{id}/progress (zero or more)
12. Android:    POST /tasks/{id}/action (zero or more)
13. Android:    POST /tasks/{id}/verification (optional)
14. Android:    POST /tasks/{id}/complete  (or /fail)        -> completed/failed
15. Desktop UI: GET /api/connect/events?stream=task:{id}     -> full sequence, stream ends
```

Offline/reconnect leg, run as its own scenario (kill the phone's network
mid-task):

```
1. Desktop UI: POST /api/connect/tasks while the phone is unreachable
                -> 201, status: queued_offline (not dispatched)
2. (phone reconnects to WiFi)
3. Android:    POST /devices/{id}/heartbeat
                -> pending_tasks includes the queued task, now dispatched
4. Android:    ack -> ... -> complete, as above
```

Revocation leg:

```
1. Desktop UI: POST /api/connect/devices/{id}/revoke
2. Android:    any signed request                -> 401 (DeviceNotTrustedError)
3. Desktop UI: POST /api/connect/pairing/start    (fresh token)
4. Android:    scan the new QR, POST .../pairing/redeem again
                -> {status: "trusted"} — the same device_id, trusted again
5. Android:    signed requests succeed again
```

Every step above already has offline-only coverage in
`tests/test_connect_offline.py` against a hand-written reference client
(§12) — what real hardware adds is everything a reference client can't
stand in for: real OS permission-grant UX for capability reporting, real
WiFi (roaming, captive portals, IPv6-only networks breaking `detect_lan_ip()`'s
assumptions), real clock drift against the 120s timestamp window, and
real Ed25519 keystore behavior (Android Keystore vs. a plain file).
