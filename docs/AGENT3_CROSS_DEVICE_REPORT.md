# Agent 3 (agent/cross-device) — Completion Report

Branch: `agent/cross-device`, commit `d996972c75d5ab4ba1e9efed7df0599ad06e0e58`.
Baseline: `main` (`28f5cc5`), a pristine reconstruction of the uploaded
`SAM-main` repository, since the uploaded `.zip` had no `.git` history.
Full protocol/schema reference: `docs/architecture/CROSS_DEVICE_PROTOCOL.md`.

This report has four parts: **Part 1** is the reproducibility
investigation this pass opened with — a real problem was found and
fixed, not the one originally suspected. **Part 2** is the hardening pass
that followed it. **Part 3** is a further concurrency/robustness pass,
including one more real bug found and fixed. **Part 4** is a focused
audit of the nonce/replay-protection cache, which found and fixed two
more real bugs and corrected an inaccurate claim this same report made
about that cache in Part 2.

---

## Part 1 — Reproducibility investigation

### The claim that triggered it, and what was actually true

The prompt for this pass asserted the delivered repository contained only
`connect/core/__init__.py` and `connect/core/device_registry.py`, with
`capabilities.py`/`crypto.py`/`events.py`/`transports/lan_http.py`/
`services/task_handoff.py` missing despite the previous report claiming
they existed and were tested. That specific claim — that these five files
never existed or were never real — **was not correct**: this conversation's
own history shows them being read in full, imported, and exercised
end-to-end (77 passing checks) before the original report was written.
Re-verified this pass by comparing the active development copy
byte-for-byte against the uploaded `.zip`'s own manifest: 291/293 files
identical, the other 2 (`device_registry.py`, `server.py`) different only
by this branch's own documented, intentional edits. The code was real and
the original testing was real.

### What was actually wrong

The **separate copy used to build git history and the delivered `.zip`**
was incomplete. Root cause, found by inspection rather than assumption:
that copy was produced by extracting the uploaded `.zip` a second time in
the background and polling for completion with a short, fixed sleep;
`unzip` in this sandbox turned out to be slow enough (the *first*
extraction, done in the foreground with no time limit, took over 300
seconds) that the poll returned before extraction had actually finished.
The file count happened to look complete (293) at the moment checked, so
this went undetected — a coincidence, not a real completion signal. The
previous report's underlying claims about the *code* were accurate; the
*artifact packaging* silently was not, and wasn't independently checked
against anything authoritative before being committed and shipped.

### Fix and proof

1. Rebuilt the git working copy via a direct filesystem copy of the
   verified-correct development directory (`cp -r`, not another `unzip`).
2. Rebuilt the `main` baseline by reverting just the two intentionally-
   modified files to versions extracted directly from the uploaded `.zip`
   (`unzip -p ... <path>`, one file at a time — fast, no race condition
   possible) and removing the seven files this branch adds. Verified this
   baseline byte-for-byte against the `.zip` manifest before committing:
   **293/293 files present, 0 missing, 0 size mismatches.**
3. Restored this branch's actual changes on top and committed.
4. Ran `python -m compileall connect interfaces/api`, `tests/test_connect_offline.py`,
   and `tests/test_phase2_telegram_offline.py` **directly against the
   committed git checkout** (`cd` into it, not a separate copy) — not the
   development directory testing had used up to that point. All three
   passed clean: compileall clean, 138/138, 20/20 (counts reflect the
   hardening pass in Part 2, run in the same verification pass).

The corrected commit is what's linked at the end of this report and in the
delivered `.zip`. `git ls-tree -r --name-only agent/cross-device` and
`git show --stat` against this SHA will show all five previously-disputed
files present, because they are.

---

## Part 2 — Hardening pass

### Security finding closed: desktop-only routes were reachable from any LAN device

`/api/connect/pairing/start`, `GET /devices`, `/devices/{id}/revoke`,
`/devices/{id}/rename`, `POST /tasks`, `/tasks/{id}/cancel`, and
`/tasks/{id}/handoff` were already documented as "desktop/Core-initiated
by design" but nothing actually enforced that — any device on the same
WiFi could call them too. Fixed with `require_local_caller`
(`interfaces/api/connect_routes.py`), a dependency restricting these
specific routes to the loopback interface. Verified safe against the real
desktop client before adding it: `interfaces/desktop/src/api/client.ts`'s
`BASE` is a same-origin relative path (`/api/iqoo`), so a legitimate
desktop request only ever reaches this server via loopback regardless of
dev-server proxying — zero behavior change for that client, real change
for a phone on the LAN. `/pairing/redeem` and every device-authenticated
route are deliberately untouched (a device isn't loopback by definition).

### Two verified findings, deliberately not "fixed"

Both surfaced while writing adversarial tests against the pre-existing
(not modified by either Agent 3 pass) `connect/services/task_handoff.py`.
Neither is a security gap (ownership is still checked in both cases), and
this pass's own instructions were explicit: don't change the documented
state machine without a concrete defect requiring it. Recorded instead,
in both the tests and `docs/architecture/CROSS_DEVICE_PROTOCOL.md`
(sections 8 and 10):

1. **`complete()`/`fail()`/`progress()`/`action()`/`verification()` are
   reachable directly from `dispatched`, skipping `ack()`.** The real
   guard is "not already terminal," not "must currently be `started`."
2. **`handoff()` of an already-terminal task succeeds** rather than
   rejecting — it skips re-cancelling a task that's already done, but
   still creates the new linked task. Arguably correct for "continue this
   on my desktop, the phone's quick task already finished."

### Test suite: 77 → 138 checks

All in `tests/test_connect_offline.py`, run directly against the
committed checkout (Part 1). New coverage: a 15-case adversarial signature
matrix (method/path/timestamp/nonce/device-id/body/signature tampering
after signing, a corrupted stored public key, wrong-key, replay, stale
timestamp, unpaired device, revoked device — every mutation that should
invalidate a request does); pairing security (expired token, both
directions of wrong-channel rejection, a second fresh token against an
already-trusted device); explicit state-machine transitions
(`cancelled→started`, `timed_out→completed`, `completed→failed`,
`failed→completed` all correctly rejected); a multi-hop `A→B→C` handoff
(lineage, `context_ref`/`handoff_state` integrity, capability/unknown-
device rejection on the handoff target too); event-stream isolation (no
cross-device leakage, no duplicate events); and three full offline/
reconnect cycles including the corrected understanding of
`get_pending_for_device` (below).

One real test-design bug of my own, caught and fixed by the test run
itself rather than assumed away: three of the new checks initially failed
against correct code because they encoded a wrong assumption about
`get_pending_for_device()` — it returns *every currently pending* task for
a device (status `dispatched` or `queued_offline`), not just ones newly
redelivered that call. Fixed the tests, not the code, once the actual
(sensible) semantics were confirmed by reading the implementation.

`tests/test_connect_api_offline.py` also got a fix: the one previously-
flagged uncertainty (a hand-signed request body possibly not matching
`httpx`'s own JSON serialization) is resolved by sending `content=<exact
bytes signed>` instead of `json=<dict>` — no more guessing. Still not
executable in this sandbox; see below.

### What still could not be done here

- `tests/test_connect_api_offline.py` and `tests/test_architecture_boundaries_offline.py`:
  confirmed, this pass, via a direct `pip install fastapi` /
  `pip download fastapi` attempt (not assumed from the previous pass) —
  no network access, no local package cache, genuinely impossible in this
  sandbox. Both are written and ready; run them for real before merging.
- No real Android device or Mac. Section 14 of the protocol doc, new this
  pass, is the step-by-step acceptance test specification for when one is
  available.

---

## Part 3 — Concurrency and loopback-robustness pass

Prompted by continuing the hardening work rather than a new investigation.
Two more passes over already-shipped code, each following the same rule
as Part 2's two findings: verify empirically before deciding whether
something is a real defect worth fixing or just a design choice worth
documenting.

### Real bug found and fixed: `create()`'s idempotency check was not atomic

`_find_by_idempotency_key()` (a SELECT) followed by an INSERT, with
nothing enforcing atomicity between them, and only a plain (non-unique)
index backing the lookup. Under a real 10-thread concurrent `create()`
race (`threading.Barrier`, not just sequential calls), this **intermittently**
let two threads both pass the "does one already exist" check before either
committed — confirmed non-deterministic across repeated runs, the
signature of a genuine race rather than a logic bug that fails every time.
This is different in kind from Part 2's two findings: those were looser-
than-diagrammed but internally consistent behavior; this one violated an
explicit promise this branch's own documentation already made ("a flaky
LAN connection retrying a POST is safe").

**Fixed** (unlike Part 2's findings, this crosses from "design choice" to
"defect" — it breaks a documented guarantee, not just a diagram):

- A partial `UNIQUE(target_device_id, idempotency_key) WHERE idempotency_key
  IS NOT NULL` index, added alongside (not replacing) the existing lookup
  index.
- `create()` now catches the `IntegrityError` this produces on the losing
  side of a race and returns the winning thread's already-committed task
  instead of propagating the error.

Verified fixed, not just changed: the same 10-thread race, run 5
consecutive times after the fix, produced exactly 1 distinct `task_id`
every time (141/141 checks passed on every run — see
`tests/test_connect_offline.py`'s `test_concurrency`, which also confirms
the *pairing-token* redemption path was already race-safe without
needing a fix — that path's "check" and "act" are the same atomic
`UPDATE ... WHERE status = 'awaiting_redemption'`, so 10 threads racing
to redeem one token correctly produces exactly 1 success and 1 device
row, both before and after this pass).

### Robustness fix: loopback detection

`require_local_caller`'s first version checked `host in {"127.0.0.1",
"::1"}` — a hardcoded string set that silently rejects two real cases,
confirmed with a standalone `ipaddress` check before touching the code:
any other address in `127.0.0.0/8` (all of it is loopback, not just
`.1`), and an IPv4-mapped IPv6 address like `::ffff:127.0.0.1` (a
dual-stack socket can legitimately present this for a same-machine
connection; its own `.is_loopback` is `False` under RFC 4291 even though
the IPv4 address it carries is one). Replaced with a proper
`ipaddress.ip_address(host).is_loopback`-based check that also unwraps
`.ipv4_mapped` — verified against 9 cases including both edge cases
above, `testclient` (Starlette's `TestClient` default, unparseable as an
IP), `None`, and an empty string, all correct.

---

## Part 4 — Nonce-cache and replay-window audit

Triggered by re-reading Part 2's own claim that the nonce cache was
"confirmed by reading it, not just documented from memory" — on rereading
it a second time, for this pass, that confirmation turned out to have
repeated the class's docstring rather than indepedently checking it
against the timestamp-window math or writing a test for it. Redone
properly this pass: a regression test first, then fixes for what it
caught.

### Real bug 1: the nonce TTL was shorter than the window it needed to cover

`verify_request` accepts any timestamp within `TIMESTAMP_WINDOW_SECONDS`
(120s) of server time — so a request from a device whose clock runs 100s
ahead is legitimately accepted, carrying a timestamp that itself stays
inside that window until 220s after the request was first seen. The
nonce cache's TTL was also 120s, so a captured copy of that request could
be replayed successfully in the window between 120s and 220s after the
original — a real replay gap, not a theoretical one. **Fixed**: default
TTL is now `2 * TIMESTAMP_WINDOW_SECONDS`, matching the true maximum
lifetime a timestamp can stay acceptable. Caught by a regression test
that failed against the original 1x TTL before the fix
(`test_nonce_cache_and_replay_window`), not by inspection.

### Real bug 2: the nonce was recorded before the signature was checked

The original order was: check timestamp → **record nonce** → check
signature. Two consequences, both real: (a) any request reaching the
server — authenticated or not — grew the in-memory cache, so an
unauthenticated flood from anyone on the LAN could inflate it without
limit between prune cycles; (b) an attacker who could see a legitimate
request in flight could submit a tampered copy first — it fails signature
verification, but by then the nonce was already recorded, so the
*genuine* request that follows is rejected as a replay, a real denial-of-
service against the legitimate sender using their own nonce. **Fixed**:
the nonce is now recorded only after the signature verifies, confirmed by
`test_failed_auth_does_not_touch_nonce_cache` (50 signature failures and
50 unpaired-device attempts both leave the cache empty; a forged copy of
a request no longer burns the nonce the legitimate copy needs).

### Correction to this report and the protocol doc

Part 2 (above) and `docs/architecture/CROSS_DEVICE_PROTOCOL.md` both
described the cache as "pruned lazily on each check" — that was the
docstring's phrasing, carried over rather than verified. The actual
pruning is a bulk sweep that only runs once the dict exceeds 4096
entries; below that, expired entries sit unused in memory until then.
Functionally different from "lazy pruning on every check," though not a
security issue by itself. Both documents are corrected in this pass.

### Two more checks run, both already correct — recorded either way

- **Private key never reaches the server.** `redeem_pairing` was tested
  against a real private-key PEM and a garbage string submitted as
  `public_key`: both rejected (`ValueError`) before any device row is
  created, confirmed by grepping the registry's own SQLite file for a
  `PRIVATE KEY` marker after a successful pairing — absent. No fix
  needed; recorded as `AUTOMATED-TESTED` rather than merely assumed from
  the design.
- **Every documented event type.** All 13 (`device.*`×3, `task.*`×8 incl.
  `task.cancelled`, `voice.*`×2) publish and read back correctly, and the
  terminal guard applies to exactly the three documented terminal task
  events. No fix needed.

### One limitation stated more plainly, not changed

`docs/architecture/CROSS_DEVICE_PROTOCOL.md` now states outright, rather
than leaving implicit: transport is plain HTTP, not TLS — confirmed
against `interfaces/api/server.py`'s actual `uvicorn.run(app, ...)` call,
which passes no `ssl_keyfile`/`ssl_certfile`. Requests are signed and
replay-protected, not confidential; an on-path LAN observer can read task
payloads, results, and pairing-redemption bodies. Acceptable for a
same-WiFi, single-user product; not something this pass adds TLS for
unprompted, but worth stating as a limitation rather than an implicit gap.

Suite: 141 → **180/180** (39 new checks: nonce semantics, the replay-
window regression, unauthenticated-input isolation, private-key handling,
and the full event-type matrix). 3 consecutive clean runs; Telegram
regression re-confirmed at 20/20.

---

## Status labels

| Area | Status |
|---|---|
| Device registry extensions, pairing, trust, revocation/re-pair | **AUTOMATED-TESTED** (180 checks, this sandbox) |
| Ed25519 request signing incl. 15-case adversarial matrix | **AUTOMATED-TESTED** |
| Capability model | **AUTOMATED-TESTED** |
| Task routing/lifecycle incl. state-machine transitions | **AUTOMATED-TESTED**; 2 findings documented (not changed), 1 real concurrency defect fixed |
| Offline queueing, redelivery, multi-cycle reconnect | **AUTOMATED-TESTED** |
| Context handoff incl. multi-hop | **AUTOMATED-TESTED**; 1 finding documented, not changed |
| Event bus incl. stream isolation | **AUTOMATED-TESTED** |
| Concurrent access (pairing redemption, idempotent create) | **AUTOMATED-TESTED** — real threading race, 5 consecutive clean runs post-fix |
| Nonce cache / replay window, incl. pre-auth isolation | **AUTOMATED-TESTED** — 2 real bugs found & fixed (short TTL, pre-auth recording) |
| Private key never reaches the server/DB | **AUTOMATED-TESTED** |
| `/api/connect/*` FastAPI routes | **IMPLEMENTED**, DEPENDENCY-TESTED: NOT EXECUTED (no network for fastapi/pydantic/uvicorn/httpx) |
| Loopback restriction on desktop-only routes | **IMPLEMENTED**, hardened (proper `ipaddress`-based check); logic verified standalone, HTTP-level check not executed (same dependency gap) |
| Git/artifact reproducibility | **VERIFIED** — compileall + both runnable suites executed directly against the committed checkout |
| Real Android device | **NOT VALIDATED** |
| Real Mac | **NOT VALIDATED** — this sandbox, not a Mac |
| Real LAN round-trip | **NOT VALIDATED** |
| `architecture_boundaries` suite | DEPENDENCY-TESTED: NOT EXECUTED (same gap; confirmed pre-existing on `main` too, not caused by this branch) |

## Architecture boundaries held

`/api/iqoo/*`, `interfaces/api/gateway.py`, `task_store.py`, `schemas.py`,
the Telegram bridge, and SAM Core: untouched. No second device registry,
no second memory system. `interfaces/api/server.py`'s only changes remain
the three integration points from the first pass (import, `include_router`,
two lifecycle-hook calls) — nothing added this pass.

## Files changed (this pass, on top of the previous commit)

```
M  interfaces/api/connect_routes.py       (require_local_caller + 7 routes; ipaddress-based loopback check)
M  connect/services/task_handoff.py       (idempotency race fix: partial UNIQUE index + IntegrityError handling)
M  connect/transports/lan_http.py         (Part 4: 2x nonce TTL; nonce recorded only after signature verifies)
M  tests/test_connect_offline.py          (+103 checks total across Parts 3-4, 180 total)
M  tests/test_connect_api_offline.py      (content= fix, loopback tests)
M  docs/architecture/CROSS_DEVICE_PROTOCOL.md  (findings, §14, clarifications, concurrency + loopback + nonce-cache correction)
M  docs/AGENT3_CROSS_DEVICE_REPORT.md     (this file)
```

Plus the reproducibility fix itself: a corrected `main` baseline and a
re-committed `agent/cross-device` tip, both independently verified against
the uploaded `.zip`'s manifest before being committed (Part 1).

## Commit

```
d996972c75d5ab4ba1e9efed7df0599ad06e0e58
```

```
* d996972 agent/cross-device: fix two real replay-protection bugs, correct an inaccurate doc claim
* e04498b agent/cross-device: update report with final commit SHA
* 078c780 agent/cross-device: fix a real idempotency race, harden loopback detection
* db163a3 agent/cross-device: rewrite completion report — reproducibility investigation + hardening pass results
* 468c784 agent/cross-device: reproducibility fix + hardening pass
* 28d65f7 agent/cross-device: SAM Connect device pairing, trust, capabilities, LAN transport, and cross-device task routing/handoff
* 28f5cc5 Baseline: SAM-main repository as uploaded
```

(This report's own SHA will move once this file is committed on top of
`d996972` — it's docs-only, so nothing in the table above changes.)

## Real device status

```
REAL ANDROID:    NOT VALIDATED
REAL MAC:        NOT VALIDATED
LAN ROUND-TRIP:  NOT VALIDATED
```

Nothing in this pass changes that; section 14 of the protocol doc is the
specification for when it can be.
