# SAM for Android — v0 (Agent 2, first slice + hardening pass + foreground-service pass + reconnect pass)

Native Android client for SAM Core, per `SAM_Master_PDR_2026-09-23.docx` §13. See the
companion `SAM_Android_Agent2_Recon_Report.md` and `SAM_Android_Agent2_Build_Report.md`
(delivered alongside this project, not inside it) for the full reconnaissance and
build status — the build report's "Hardening pass" addendum is the most direct
answer to "is this actually buildable and tested yet"; its Phase 3 and Phase 4
addenda cover the foreground service and the reconnect. This file covers just
what's in this project folder.

## Status, in one line

**Type-checked against a hand-built harness, and `TaskMonitor`'s logic has been
executed on a real coroutines runtime — but the project has still never been
built with Gradle, never run through JUnit, and never run on a device or
emulator.** No Android SDK, emulator, or real device was available in the
environment this was written in, and a direct network test confirms this
environment cannot reach `dl.google.com`, `maven.google.com`,
`repo1.maven.org`, or `services.gradle.org` at all — so a real Gradle sync
isn't just "not attempted," it's confirmed not possible from here. As a
substitute, the real Kotlin 2.0.21 compiler (not a real Gradle/AGP build) was
run against every non-UI source file and every test file using hand-written
stubs standing in for Android/AndroidX/OkHttp/JUnit. Result: clean, except
three `DeviceInfo.serializer()`-style calls that need kotlinx.serialization's
own compiler plugin (unavailable here — Maven-only distribution); against the
unmodified files those are the *only* diagnostics (8 lines, all at or caused by
the 3 call sites: 3 "unresolved reference", 4 type-inference follow-ons at two of
them, and one "unresolved reference `copy`" on the line after the `TaskEvent` call). The
Compose UI layer was not re-checked in the foreground-service or reconnect passes
(see the build report's Phase 3 and Phase 4 addenda). Separately, `TaskMonitor`
was run — real class, the project's own test fakes, real threads — through 38
scenarios (all pass, 25 runs in a row, and 23 bugs deliberately re-introduced
one at a time were each caught by at least one scenario). That is real signal
about the logic; it says nothing about Android itself. The **foreground service
has never run on any Android**, and the reconnect has never talked to a real
server or a real OkHttp client. See the build report for exactly what each of
these does and doesn't prove.

## Opening this project

1. Android Studio (Koala/2024.1+) → Open → select this folder.
2. Studio will offer to generate the Gradle wrapper jar — accept it. `gradle/wrapper/gradle-wrapper.properties`
   is included (pinned to Gradle 8.9) but `gradle-wrapper.jar` itself is a binary this
   environment couldn't fetch. If Studio doesn't offer, run `gradle wrapper` once with
   any locally-installed Gradle 8.x (not the `apt`-packaged Gradle 4.4.1 — too old for AGP 8.x).
3. Let Gradle sync. This needs real network access to `google()` and `mavenCentral()`.
4. Run `./gradlew test` — unit tests exist now (`app/src/test/`) and have never been executed;
   this should be the very first thing run, before installing anything.
5. Run on a device or emulator running Android 8.0 (API 26) or newer for the manual flows
   listed in the build report's device-validation checklist.

## What's implemented

- Project/module setup: Gradle Kotlin DSL, version catalog (`gradle/libs.versions.toml`), Compose enabled.
- Theme (`ui/theme/`): colors sampled directly from `SAM_LOGO.png` (`#FD6902` / white), dark-only per PDR §7 — light mode not implemented.
- `data/transport/SamTransport.kt`: the interface everything else is built against.
- `data/transport/HttpSseSamTransport.kt`: v0 implementation. Task/health/event endpoints shaped after the real `docs/iqoo/PROTOCOL.md` in the main repo; **the pairing endpoint (`POST /api/connect/pair`) is an invented placeholder** — no existing HTTP pairing endpoint was found during reconnaissance. See the class doc comment. Uses a separate client for the SSE connection with a **finite 60 s read timeout** (a default 10 s client timeout would have killed long-idle task streams; an infinite one — what the hardening pass used — would let a half-open connection hold the foreground service open until `TaskMonitor`'s cap). The 60 s figure is a **provisional assumption** derived from the repo server's ~1 s heartbeat (`interfaces/api/server.py`), not from a documented contract: Agent 3's contract has to state a heartbeat interval well under it. Explicit timeouts for everything else too. `taskEvents(taskId, afterSeq)` can resume a dropped stream: it sends the SSE `Last-Event-ID` header, which `interfaces/api/server.py` honors (replays only events with a higher `seq`) but `docs/iqoo/PROTOCOL.md` does not mention — provisional until Agent 3's contract says. Each event's `TaskEvent.seq` is filled in from the SSE `id:` line. `getTask`/`sendTask` now report a body they cannot decode (invalid JSON, or a status the app's `TaskStatus` does not list — the repo's task store also accepts `testing`) as a failed `TransportResult` instead of letting the exception escape.
- `data/local/PairedDeviceStore.kt` (interface) / `DevicePrefsStore.kt` (real DataStore-backed implementation): local persistence of the paired device. Split into an interface specifically so `HttpSseSamTransport` is unit-testable without a real Android `Context`.
- `notifications/TaskNotifier.kt` (interface) / `SamNotifications.kt` (real implementation): same reasoning, for `TaskMonitor`.
- Four screens + ViewModels: Onboarding, Pairing, Connection & device state, Task status (with live SSE event list).
- Navigation (`ui/navigation/SamNavGraph.kt`): loading → {onboarding | connection} → pairing → connection → task status.
- Task-completion notifications (`notifications/`): a notification channel, a runtime `POST_NOTIFICATIONS` request made at the point it's relevant (sending a task) rather than at launch, and an app-scoped `TaskMonitor` that keeps watching a task's events even if the user backs out of the task-status screen — so the notification can still fire. It survives navigating between screens within one app session; whether it survives the app being backgrounded is what the foreground service (next item) is for — **unverified on any device**. The terminal-status check (only notify when the task is actually done) lives in `TaskMonitor`, not guessed from SSE `phase` strings — see `TaskMonitorTest`.
- **Foreground service for in-flight tasks** (`notifications/TaskKeepAlive.kt`, `TaskWatchForegroundService.kt`, `TaskMonitor.isWatching`): when `TaskMonitor` starts watching a task it asks for a `dataSync`-type foreground service, which shows a low-importance ongoing notification (generic text — no task instruction on the lock screen) and **stops itself** as soon as the watch ends, however it ended. Goal: lower the odds that Android freezes or kills the process while the user is in another app or the screen is off. Design points that matter if you change it: the service is start-only from outside (no `stop()` — stopping from outside can race its start-up); it calls `startForeground()` first thing; it ends with `stopSelf(startId)`; `START_NOT_STICKY`; it handles Android 15's `onTimeout`. Scope note: the earlier hardening brief said *not* to implement a foreground service; this was added after "go for the next phase", and is isolated so it can be dropped (see the build report's Phase 3 addendum).
- `TaskMonitor` hardening that came with it: every write a watch makes to shared state (snapshot, events, announcement) is made under a lock and only if that watch is still the current one, so a watch that was just replaced or stopped cannot overwrite the new watch's state; each watch is also bounded (default 30 min, **provisional**) so a stream that stays open but never finishes can't pin the service forever.
- **Bounded reconnect** (`TaskMonitor`, added after the foreground-service pass; **the reconnect-pass item that was listed as the next step**): when a stream ends, `TaskMonitor` asks for the authoritative status. Terminal → announce once and end, as before. Still running, or the lookup failed (usually: the network is down) → wait, then open a new stream that resumes after the last event already shown. The wait before each consecutive reconnect that follows a connection that delivered nothing new is `1 s, 2 s, 4 s, 8 s, 16 s` (default, **provisional and unmeasured**); when those five are spent the watch ends silently, exactly as it did before this pass. A connection that delivers a new event restores the whole budget. The 30 min cap still bounds everything, and `isWatching` stays true while waiting so the foreground service stays up. Replayed events are skipped by `seq`; events that arrive *without* a `seq` are never replayed (the watch just ends). Passing an empty list for `reconnectBackoffMillis` turns reconnecting off — the whole reconnect pass can be dropped that way, or by reverting its patch.
- Manifest permissions: `INTERNET`, `ACCESS_NETWORK_STATE`, `POST_NOTIFICATIONS` (now actually requested and used, not just declared), `FOREGROUND_SERVICE` and `FOREGROUND_SERVICE_DATA_SYNC` (the latter is required from Android 14 for a `dataSync` service; targetSdk is 35).
- A network security config permitting cleartext HTTP app-wide, scoped to this app's single-purpose use case and documented why (see the file itself) — the initial CIDR-based draft was wrong and was corrected after checking Android's own docs.
- `android:allowBackup="false"` in the manifest (paired-device info shouldn't ride along in a phone backup/restore to a different device) — this was already in place, confirmed still here during this pass. No logging anywhere in the app, so nothing to check for leaking the pairing code or address into logs.
- **Unit tests** (`app/src/test/`, 53 `@Test` methods): `HttpSseSamTransport` (19 — pairing, connection state, task CRUD, SSE framing incl. heartbeat lines, the finite SSE timeout, the `Last-Event-ID` header and `seq` from the `id:` line, undecodable task bodies, unpair — against `MockWebServer`, not a real network) and `TaskMonitor` (34 — event collection, the terminal-only notification gate, watch cancellation, keep-alive request, `isWatching` in every way a watch can end, the cap in virtual time, stale work from a replaced/stopped watch, and 13 reconnect tests on a hand-driven virtual clock that assert the wait schedule to the millisecond). Type-checked against the harness; **never executed by JUnit** — see the build report. (The earlier reports' "11 / 17 tests" was a miscount; the Phase 3 files had 14 + 21 = 35.) The `TaskMonitor` behaviours were additionally executed as plain-`main` scenarios on a real coroutines runtime — see the build report's Phase 3 and Phase 4 addenda for what that does and doesn't establish.

## Known gaps in the foreground-service and reconnect work (also in the build report)

- **Not run on any device or emulator.** All OS behaviour here comes from Android's documentation, not observation.
- **Does not survive the process being killed.** `START_NOT_STICKY`, nothing persisted: a foreground service lowers the odds of being killed, it does not recover from it. vivo/iQOO's own battery managers may still kill the app; that is unmeasured.
- **Reconnect is bounded and blunt.** When the backoff schedule is spent (31 s of waiting in total with the defaults, plus however long each attempt takes to fail — up to about 70 s for a stream attempt (10 s connect + 60 s read timeout) and 25 s for a status lookup, so roughly 10 minutes if every one of the 6 attempts hangs; arithmetic, not measured) the watch ends silently and the user is not told when the task finishes later. It cannot tell a permanent failure from a transient one (`TransportResult.Failure` carries no HTTP status), so a task the server no longer knows, a revoked pairing or an unpaired app use up the whole budget before it gives up. It does not wait for connectivity (no `ConnectivityManager` callback), the UI is not told it is reconnecting, and it does not detect a gap in `seq`. The reconnect depends on `server.py` behaviour (`Last-Event-ID`, `seq` numbering) that `PROTOCOL.md` does not describe.
- **Silent when Android refuses to start the service** (e.g. Android 12+ background-start limits): the watch proceeds without keep-alive and there is no UI signal.
- Neither the ongoing nor the completion notification has a tap action (no `contentIntent`).
- The 60 s SSE timeout, the 30 min watch cap and the reconnect schedule are provisional (see above). If a future server sends no heartbeat, idle streams would be cut at 60 s and the watch would burn through its reconnect budget and end without a notification.
- Battery cost of holding a ~1 Hz-heartbeat connection open is unmeasured.
- `TaskMonitor.stopWatching()` has no production caller yet (tests only); one task at a time. Unpairing mid-task does not stop the watch either; it just fails its reconnects until the budget is spent.
- `TaskStatus` has no `testing` value although the repo's task store accepts one (`interfaces/api/task_store.py`, `ALL_STATUSES`; `PROTOCOL.md` says it is "not yet emitted by anything in Phase 1 or 2"). A status lookup that lands on it is reported as a failed lookup, not shown. Not changed here.

## What's deliberately not in this slice

- Voice entry, wake-word — PDR §13 asks for both; still queued.
- Light theme.
- Edge-to-edge inset handling per-screen (`enableEdgeToEdge()` is called in `MainActivity`, but individual screens don't yet apply `WindowInsets` padding — content may sit under system bars on some devices).
- A real launcher icon (also reused as the notification's small icon) — the adaptive icon uses the real sampled SAM orange with a simple placeholder mark, not a traced version of the actual logo. Swap via Android Studio's Image Asset Studio.
- Token expiry/refresh and server-side revocation — "Unpair" only forgets local state; there's no endpoint to tell SAM Core to stop trusting this device, any more than there's a confirmed pairing endpoint.
- ViewModel-level tests, and ones needing Robolectric/instrumentation — out of scope for "focused tests that don't need a physical device."

## What wasn't possible here

No Android SDK, no emulator, no physical device. Beyond that, this pass specifically
tested (not assumed) whether a real Gradle build could work at all: `curl` against
`dl.google.com`, `maven.google.com`, `repo1.maven.org`, and `services.gradle.org` all
came back `403` with `x-deny-reason: host_not_allowed`, and the only Gradle available
through this environment's package manager is version 4.4.1 (2017-era, incompatible
with AGP 8.x regardless). So: zero Gradle syncs, zero compiles, zero lint passes, zero
of the new unit tests actually executed, zero installs, zero taps on a real screen —
all confirmed impossible from here, not just "not gotten to." (The foreground-service
pass added one real execution path — `TaskMonitor` run on a plain JVM against the
project's own fakes, extended to the reconnect logic in the Phase 4 pass — but
that is a stand-in for the JUnit run, not the JUnit run. The transport's new
`Last-Event-ID` and `id:` handling has only been type-checked: `MockWebServer`
and `okhttp-sse` are Maven-only and were never available to run.) If this sandbox's
network allowlist can be extended, adding those four hosts is what would unblock a
real build; otherwise this needs Android Studio, Claude Code with real network access,
or a real machine.

Every file was written and re-read by hand against Kotlin/Compose/Navigation/OkHttp/
kotlinx-coroutines-test semantics, with the highest-risk assumptions (network security
config syntax, `okhttp-sse`'s exact Maven coordinate, `popUpTo`'s string-route API,
`Modifier.weight`'s import rules) checked against current documentation rather than
assumed. That caught real mistakes (see the build report's "bugs found" list, now
including a missing SSE read-timeout override found in this pass) — which is evidence
this was done carefully, not evidence it's correct. A compiler would still very likely
find things this process didn't.
