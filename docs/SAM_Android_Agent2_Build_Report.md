# SAM Android (Agent 2) — Build Report, First Slice

Structured against the 12 points the original Agent-2 brief asked for as final output.
Companion to `SAM_Android_Agent2_Recon_Report.md` (read first if you haven't) and the
project itself (`SAM_Android_v0_Agent2.zip`), which also contains its own `README.md`.

> **Later passes supersede parts of this section.** The paragraph below describes the first slice only. What has since been type-checked and executed — and what still has not — is recorded in the *Hardening pass*, *Phase 3 addendum* and *Phase 4 addendum* sections further down.

**Read this whole report before trusting any single line in it** — point 7 and 9 in
particular mean everything below was written and manually reviewed, not compiled,
run, or tested. That's not a formality: point 10 lists four real mistakes this
process caught and fixed along the way, which is direct evidence more may remain
uncaught in whatever a real build turns up first.

## 1. Android architecture

Kotlin + Jetpack Compose, MVVM with `StateFlow`, manual DI (`AppContainer` — no
Hilt; see its doc comment for why), OkHttp + `okhttp-sse` for networking,
DataStore for local persistence. Single-activity, Navigation Compose for screens.

```
UI (Compose screens)
      │
ViewModels (StateFlow)
      │
SamTransport  ← interface: restore(), pair(), checkConnection(), connectionState,
      │          sendTask(), getTask(), taskEvents(), cancelTask(), unpair()
      │
HttpSseSamTransport (v0) — OkHttp + okhttp-sse against SAM Core's HTTP API
```

The `SamTransport` interface is the one deliberate architectural bet in this
slice: everything above it is written against the interface, not the HTTP
implementation, specifically so that Agent 3's real cross-device contract can
land as a new implementation later without touching any screen or ViewModel.

## 2. Features implemented

- Onboarding (identity + one CTA)
- Pairing (form → `SamTransport.pair()` → persists via DataStore)
- Connection & device state (status indicator, manual health check, unpair)
- Task status (send an instruction, live SSE event list, cancel)
- Navigation across all four, with initial-route resolution based on whether a device was already paired (survives process death / relaunch)

Not implemented (see recon report §5 and this project's README for the full list): notifications, background/foreground service, voice entry, wake-word, light theme.

## 3. Permissions implemented

`INTERNET`, `ACCESS_NETWORK_STATE` — declared, used immediately (every network call).
`POST_NOTIFICATIONS` — declared in the manifest only. Nothing in this slice requests
it or posts a notification, so there's no runtime request flow to describe yet;
it's there so the second slice (notifications) doesn't need a manifest change.
No other permissions requested — no microphone, no background service, no
storage access in this slice.

## 4. Device identity / pairing work

`DeviceInfo` (device_id, device_name, channel) mirrors `connect/core/device_registry.py`'s
schema. `DevicePrefsStore` persists the paired device + base URL locally via
DataStore so the app opens straight to the connection screen after the first
pairing. The pairing **screen and flow** are implemented end-to-end on the
Android side; the pairing **endpoint** it calls (`POST /api/connect/pair`) is
an invented placeholder — reconnaissance found no existing HTTP pairing
endpoint anywhere in the repo (today's real pairing is a Telegram bot command
flow). This is flagged in three places on purpose (recon report, this report,
and the code's own doc comment) so it doesn't get mistaken for a confirmed contract.

## 5. Cross-device interfaces exposed

The `SamTransport` interface (`data/transport/SamTransport.kt`) is the concrete
answer to "what does the Android client expect from the other side": pair,
check connection, send/get/cancel a task, stream task events, forget a device.
`SamTransportModels.kt` gives the exact shapes (`DeviceInfo`, `TaskRequest`,
`TaskSnapshot`, `TaskEvent`, the `TaskStatus` state machine) — grounded in
`docs/iqoo/PROTOCOL.md` for everything except pairing (see §4). This is what
Agent 3 has to either confirm or correct.

## 6. Files changed

All 38 paths are new (first slice, nothing pre-existing to modify):

```
README.md
app/build.gradle.kts
app/proguard-rules.pro
app/src/main/AndroidManifest.xml
app/src/main/java/com/samcore/android/AppContainer.kt
app/src/main/java/com/samcore/android/MainActivity.kt
app/src/main/java/com/samcore/android/SamApplication.kt
app/src/main/java/com/samcore/android/data/local/DevicePrefsStore.kt
app/src/main/java/com/samcore/android/data/transport/HttpSseSamTransport.kt
app/src/main/java/com/samcore/android/data/transport/SamTransport.kt
app/src/main/java/com/samcore/android/data/transport/SamTransportModels.kt
app/src/main/java/com/samcore/android/ui/ViewModelFactory.kt
app/src/main/java/com/samcore/android/ui/connection/ConnectionStateScreen.kt
app/src/main/java/com/samcore/android/ui/connection/ConnectionViewModel.kt
app/src/main/java/com/samcore/android/ui/navigation/SamNavGraph.kt
app/src/main/java/com/samcore/android/ui/onboarding/OnboardingScreen.kt
app/src/main/java/com/samcore/android/ui/pairing/PairingScreen.kt
app/src/main/java/com/samcore/android/ui/pairing/PairingViewModel.kt
app/src/main/java/com/samcore/android/ui/taskstatus/TaskStatusScreen.kt
app/src/main/java/com/samcore/android/ui/taskstatus/TaskStatusViewModel.kt
app/src/main/java/com/samcore/android/ui/theme/Color.kt
app/src/main/java/com/samcore/android/ui/theme/Theme.kt
app/src/main/java/com/samcore/android/ui/theme/Type.kt
app/src/main/res/drawable-nodpi/sam_logo.png
app/src/main/res/drawable/ic_launcher_background.xml
app/src/main/res/drawable/ic_launcher_foreground.xml
app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml
app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml
app/src/main/res/values-night/themes.xml
app/src/main/res/values/colors.xml
app/src/main/res/values/strings.xml
app/src/main/res/values/themes.xml
app/src/main/res/xml/network_security_config.xml
build.gradle.kts
gradle.properties
gradle/libs.versions.toml
gradle/wrapper/gradle-wrapper.properties
settings.gradle.kts
```

## 7. Tests executed

**None.** No unit tests or instrumented tests were written for this slice, and
none could be run — no Android SDK, no JVM test runner wired up, no emulator.

## 8. Real-device test results

**None.** No device or emulator was available in this environment. Nothing in
this report should be read as "verified working" — see the environment note
below.

## 9. Android limitations (of this environment, not of Android)

No Android SDK, no Gradle distribution reachable (`services.gradle.org` isn't
on this environment's network allowlist), no `google()`/`mavenCentral()`
access to resolve AndroidX/Compose/OkHttp, no emulator, no physical device.
Concretely: zero Gradle syncs, zero compiles, zero lint passes, zero test
runs. Every file was hand-written and manually re-read against Kotlin/Compose/
Navigation/OkHttp semantics I was confident about, with four specific points
double-checked against current documentation rather than assumed (listed in
§10). That's real diligence, but it is not a substitute for a compiler.

## 10. Known bugs

None *known* in the sense of "observed failing" — nothing has run. What I can
honestly report instead is what manual review caught and fixed while writing
this, since it's the closest available signal to "how careful was this code":

- `network_security_config.xml` originally tried CIDR ranges (`192.168.0.0/16`) in a `<domain>` element — checked against Android's own docs, confirmed that's not valid (domain-config only matches exact hostnames/IPs), corrected to a documented `base-config` with an explanation of the tradeoff.
- `SamNavGraph.kt` originally cleared the back stack with `popUpTo(0)` — that's the old Int-destination-ID API; this graph uses string routes, where `0` matches nothing. Corrected to `popUpTo(navController.graph.findStartDestination().id)`, the documented pattern.
- `TaskStatusScreen.kt` originally imported `Icons`/`ArrowBack` from a package that doesn't exist (`androidx.compose.material3.icons`, not a real path) for an icon that wasn't even used — removed rather than fixed, since nothing in this slice needs an icon.
- `ConnectionViewModel.kt` originally exposed `transport.connectionState` via an unsafe cast to `StateFlow` — replaced with `.stateIn(...)`, the correct way to turn a plain `Flow` into a `StateFlow` without assuming anything about the implementation behind the interface.

Take this list as "the kind of thing that was wrong once already," not as a
complete list of what's wrong now.

## 11. Requirements for Agent 3

- A real pairing endpoint (or equivalent mechanism) to replace the placeholder in `HttpSseSamTransport.pair()` — shape, path, and how a pairing code gets validated are all open.
- Confirmation (or correction) of the task/event contract this slice assumed from `docs/iqoo/PROTOCOL.md` — field names, the state machine, SSE event shape.
- A decision on how the app resolves SAM Core's address (manual entry, as built here, vs. mDNS/`.local` discovery vs. something else) — affects both the pairing UX and whether `network_security_config.xml`'s cleartext scope can ever be narrowed from app-wide to a specific host.

## 12. Exact commit SHA

**N/A.** This was written from an extracted zip with no `.git` history, in a
session with no push access to the actual repository. There is no commit to
cite. If a baseline SHA gets frozen per PDR §17, this project should be
re-diffed against it rather than assumed compatible.

---

## Addendum — second increment: task-completion notifications

Added after this report's first version, on the same "no build/test/device
available" basis as everything above — same caveats apply throughout.

**What was added:** `notifications/SamNotifications.kt` (channel + posting,
checking `POST_NOTIFICATIONS` immediately before every call rather than
trusting an earlier request) and `notifications/TaskMonitor.kt` (an
application-scoped — not `viewModelScope` — watcher, held in `AppContainer`,
so a task keeps being observed if the user backs out of the task-status
screen before it finishes). `TaskStatusViewModel` now delegates live
snapshot/event observation to `TaskMonitor` instead of calling
`SamTransport.taskEvents()` itself; sending and cancelling a task still go
straight through `SamTransport`. `TaskStatusScreen` now requests
`POST_NOTIFICATIONS` (API 33+ only) at the point a task is first sent, not at
launch, and doesn't block sending on the result.

**Deliberately not attempted:** a real foreground/background service.
Everything above survives navigating between screens in one app session; none
of it survives the OS killing the app process (Doze, swipe-away, low memory).
Overstating that distinction is exactly what PDR §18 ("do not fake native OS
capabilities," "do not claim Android support without real-device validation")
warns against, so it's called out here plainly rather than left implied.
Voice entry and wake-word remain queued behind the service, unchanged from
the original recon report's plan.

**One design point worth flagging rather than burying:** detecting "this task
is actually finished" doesn't pattern-match the SSE events' `phase` string
against a guessed set of terminal values — reconnaissance didn't leave enough
certainty about that field's exact vocabulary to rely on it. Instead,
`TaskMonitor` waits for the event stream itself to end (which `PROTOCOL.md`
describes the server doing once a task reaches a terminal state) and then
asks for the task's authoritative status directly, so a guess about string
values isn't load-bearing for whether a notification fires.

Files touched beyond the original 38: `notifications/SamNotifications.kt` and
`notifications/TaskMonitor.kt` (new); `AppContainer.kt`, `SamApplication.kt`,
`TaskStatusViewModel.kt`, `TaskStatusScreen.kt`, `SamNavGraph.kt`,
`MainActivity.kt` (modified to wire `TaskMonitor` through). No files were
removed. `SAM_Android_v0_Agent2.zip` has been replaced with the updated
project; this report and the recon report are otherwise unchanged.

---

## Coverage check against the original Agent-2 prompt, section by section

Asked directly, so answered directly and completely — not just the parts
already covered above. ✅ built · ⚠️ partial, with the real gap named · ❌ not
started.

**§3 Android experience** — ✅ onboarding, pairing, SAM identity, task/chat
interface, task status, connection state, notifications (completion only).
⚠️ device registration (captured, no separate concept from pairing) · trust
state (binary paired/not-paired only) · offline state (status shown, no
dedicated offline-mode handling) · permission management (notifications
only, no central screen). ❌ voice interaction · wake-word/background
interaction · app/device actions.

**§4 Android capabilities** — ✅ task/result display, notifications (narrow).
❌ application launching · Android intents · microphone · foreground/
background service · voice input · accessibility/device-control mechanisms.
This section is mostly about Android exposing capabilities *to* SAM Core —
none of that direction is built; everything so far is the reverse (Android
*consuming* SAM Core).

**§5 Wake word/voice** — ❌ not started, including the fallback the prompt
itself asks for: if background wake-word isn't reliably implementable,
document why, the permissions, battery implications, and foreground-service
requirements. That documentation exercise hasn't happened either.

**§6 Device identity** — ✅ pairing flow, connection state. ⚠️ registration,
trust (as above). **Revocation is weaker than it looks**: "Unpair" only
clears local app state (DataStore) — it does not call SAM Core to revoke
trust server-side, because no such endpoint exists any more than the pairing
one does. Worth reading that as "forget" rather than "revoke" until Agent 3's
contract defines real revocation. ❌ rename/display name.

**§7 Cross-device contract** — ✅ documented (`SamTransport.kt` +
`SamTransportModels.kt` + both reports).

**§8 Security** — ✅ local storage (nothing beyond device_id/name/base_url —
no long-lived secret), permission boundaries for what's built. ⚠️ pairing
tokens (a code is entered, no expiry/refresh logic). ❌ **secure
communication** — traffic is cleartext HTTP, not TLS, app-wide (documented
and reasoned through in `network_security_config.xml`, but still a real gap,
not a solved one) · revocation (see §6).

**§9 UI** — ✅ SAM-orange identity from real sampled colors, dark-first,
mobile-native IA (not a copy of the desktop layout — though this was never
actually seen to compare against, just built independently from the same
brand spec). ❌ "restrained holographic active states" · dedicated
typography (system font only).

**§10 Testing** — ❌ **entirely unfulfilled.** Nothing in this project has
run: no install, no pairing, no reconnect, no offline behavior, no
notification actually firing, no voice, no background behavior, no app
launching, no task request, no result display, no device identity flow, no
revocation — on a real device or otherwise. This is the single largest gap
relative to what the prompt asked for, and everything else in this report
should be read through that lens.

**§11 Branch discipline** — ✅ in spirit (nothing outside Android was
modified, no other agent's territory touched) — though there's no real git
branch in this environment to actually hold this to.

**§12 Stop conditions** — the two that actually fired (missing pairing
endpoint, missing frozen §16 contracts) were reported, not silently worked
around — see the recon report and §4/§11 above.

**§13 Final output** — ✅ this report.

**Bottom line:** the request/response loop — pair, check connection, send a
task, watch it live, get notified — is real, reviewed code end to end.
Voice, wake-word, the background service, Android-side capabilities exposed
*to* SAM Core, deeper security (token expiry, real revocation, TLS), and
*all* real-device testing are the actual remaining scope, not polish on top
of a finished thing.

---

## Hardening pass — required final report

Answering the specific brief to turn this from "manually reviewed" into
"buildable and testable," structured exactly as requested. Short version:
**the build/test infrastructure itself is confirmed unreachable from this
environment** — not skipped, not assumed, tested directly — so this pass
did everything else the brief allowed for and documents the blocker
precisely rather than working around it by pretending.

### A. Build status

| Check | Result |
|---|---|
| Gradle configuration/sync | **FAIL — environment, not project.** Direct `curl` to `dl.google.com`, `maven.google.com`, `repo1.maven.org`, `services.gradle.org` all returned HTTP 403 with header `x-deny-reason: host_not_allowed`. `apt` has only Gradle 4.4.1 (2017), incompatible with AGP 8.7.2/Kotlin 2.0.21 regardless of network access. There is no path to a real Gradle/AGP build from this sandbox. |
| Compilation (real Gradle/AGP) | **NOT RUN** — blocked by the above. |
| Kotlin-level type-check (this session's own harness) | **PASS, with one named exception** — see "What the harness pass actually proves" below. Not a substitute for the row above. |
| Lint | **NOT RUN**. |
| Unit tests | **Compile clean under the harness; never executed.** See §C. |

Per the requested distinction: the Gradle/AGP row is category 3, a **local
environment failure** (no egress to the required hosts), not a project/code
failure or an ordinary dependency-resolution failure (the dependency
coordinates themselves were separately verified against current
documentation earlier in this report). If this sandbox's allowed-domains
list can be extended, those four hosts are specifically what's missing.

**What the harness pass actually proves, and doesn't.** Since a real build
was confirmed impossible, this pass went one step further than manual review:
the official Kotlin 2.0.21 compiler (`kotlinc`, fetched from Kotlin's own
GitHub releases — an allowed host, not Maven) was run directly against every
`.kt` file in `app/src/main` and `app/src/test`, on a classpath built from
the real `kotlin-stdlib`/`kotlinx-coroutines-core` jars (bundled with that
same compiler download) plus roughly 40 small hand-written stub files
standing in for Android, AndroidX/Compose, OkHttp, JUnit, and
kotlinx-coroutines-test — none of which are fetchable from this sandbox.
Each stub's method signatures were written to match the real library's
documented shape (several, like `Modifier.weight`'s import rules and
`okhttp3`'s companion-scoped `toRequestBody`/`toMediaType`, were the exact
things a previous pass of this project got wrong and had to correct — this
harness deliberately re-tests those). The first run surfaced 843 diagnostics;
after fixing the stubs (not the app code) to match verified real shapes, the
final run comes back with **5 errors, all four tracing to one cause**: calls
to `DeviceInfo.serializer()` / `TaskSnapshot.serializer()` / `TaskEvent.serializer()`
depend on kotlinx.serialization's own compiler plugin generating a companion
object at build time — that plugin needs the real `kotlinx-serialization-core`
runtime, which (confirmed by search) is published only to Maven repositories,
none reachable from here. Every other line in both source sets — roughly
1,900 lines across 28 files — type-checks cleanly against these
faithfully-modeled stand-ins.

Read that as real, useful signal, not as "it builds": a stub is still a
stand-in written by the same process that wrote the app code, not the actual
library. It cannot catch a real Gradle/AGP-level problem (manifest merging,
resource linking — the `R` class here is hand-typed from two known
references, not generated by AAPT from real XML — ProGuard/R8, multi-module
wiring, the version catalog's own syntax) or confirm the tests *pass*, only
that they and the app *compile* against shapes this session is confident are
right. The three `.serializer()` call sites are the one place even that
narrower claim doesn't apply — left unverified and named here rather than
worked around.

### B. Tests added

`app/src/test/java/com/samcore/android/`:

- **`data/transport/HttpSseSamTransportTest.kt`** (11 tests) — against `MockWebServer`, not a real network: `restore()` resolving to Disconnected/Connected; `pair()` success persisting the device and updating `connectionState`; `pair()` on an HTTP error persisting nothing; `pair()` on an unparseable 200 body failing cleanly instead of throwing; `checkConnection()` before pairing failing with zero network calls; `checkConnection()` success and failure; `sendTask()` happy path and HTTP-error path; `getTask()` happy path; `cancelTask()` happy path and HTTP-error path; `unpair()` clearing both the persisted store and the in-memory base URL (checked by confirming a post-unpair call fails with "Not paired," not a stale HTTP call).
- **`notifications/TaskMonitorTest.kt`** (6 tests) — against fakes, no Android framework: events accumulate as they're emitted; the stream ending triggers an authoritative `getTask()` call; the notifier fires when that authoritative status is terminal; the notifier does **not** fire when a dropped stream's authoritative status turns out to still be running (the exact false-positive the design is meant to prevent); the notifier does not fire when the authoritative lookup itself fails (and the last-known snapshot is left alone, not blanked); starting a new `watch()` cancels a still-open previous one.
- **`fakes/`** — `FakePairedDeviceStore`, `FakeSamTransport`, `FakeTaskNotifier`: hand-written test doubles, not a mocking library (avoids adding Mockito/MockK as a dependency for a handful of simple interfaces).

**Not written:** ViewModel-level tests, anything needing Robolectric or
instrumentation. Out of scope for "focused tests that don't need a physical
device," and adding Robolectric would be a heavier dependency change than
this pass should make unasked.

### C. Tests actually executed

**Zero.** All 17 tests above were written, manually traced through by hand,
statement by statement, and — new this pass — confirmed to **compile**
cleanly against the Kotlin-frontend harness described in §A. Compiling is
not running: nothing evaluated a single `assertEquals`, no JUnit runner ever
started, and `./gradlew test` never happened. Per the explicit rule for this
report, none of these 17 are claimed as passing — only as no longer
containing a type error or unresolved reference, which is a real but
strictly smaller claim.

One test in particular is worth flagging as the least certain even by that
manual standard: **`watching a new task cancels the previous still-running
watch`** relies on precise `UnconfinedTestDispatcher` cancellation-ordering
semantics that are exactly the category of thing most likely to need
adjustment on a first real run, more so than the others.

### D. Device validation

- Emulator/device available: **No.**
- APK installed: **No** — and there is no APK to install, because
  compilation itself never ran (§A). The brief's fallback ("if compilation
  succeeds, produce the APK") doesn't apply; compilation didn't get that far.
- Actual flows tested: **No.** Every item in the 12-step flow from the brief
  (fresh launch → onboarding → pairing → connection check → send task →
  SSE events → completion → notification → navigate away → return → unpair →
  relaunch/persistence) remains untested on real Android, exactly as the
  previous version of this report already stated.

### E. Bugs found and fixed (this pass)

One new issue, found by re-reading the transport code specifically looking
for this class of problem (the four from the original build are unchanged,
listed there — not repeated here to avoid duplicating one report inside another):

- **Symptom:** a long-running task's live SSE status would likely stop
  updating partway through, with no error surfaced to the user beyond the
  stream just going quiet.
- **Root cause:** `HttpSseSamTransport` passed its single `OkHttpClient` —
  default 10s read timeout — to `EventSources.createFactory()` for the task
  event stream. `docs/iqoo/PROTOCOL.md` sends heartbeat comments "during idle
  gaps," but nothing established those arrive more often than 10 seconds, and
  a task can sit in one phase (e.g. `executing`) far longer than that with no
  new event at all. OkHttp's default read timeout applies to gaps between
  incoming data on a streaming response, not just initial connection — an
  idle SSE connection past that window is torn down as a timeout.
- **Fix:** added a second, SSE-only `OkHttpClient` (`sseClient`, in
  `HttpSseSamTransport.kt`) derived from the base client via `.newBuilder()`
  with read timeout disabled (`0` = infinite), used only for
  `EventSources.createFactory()`. Regular request/response calls (pair,
  health, task CRUD) keep an explicit, finite timeout on the base client —
  previously implicit defaults, now explicit (10s connect/write, 15s read).
- **Verification:** none available — this is a real-device/real-server
  behavior; nothing about it can be confirmed without both. Flagged here as
  "fixed" in the sense of "the code no longer does the obviously-wrong
  thing," not "confirmed correct."

### F. Remaining blockers

- **Build/test execution itself** — needs an environment with real network
  access to Google's and Maven Central's repositories (see §A). This is now
  the most concrete, specific blocker, ahead of the product-level ones below.
- **Pairing contract** — `POST /api/connect/pair` remains an invented
  placeholder; no existing HTTP pairing endpoint was found in the repo.
- **Agent 3's cross-device contract** — task/event shapes are still assumed
  from `docs/iqoo/PROTOCOL.md`, built for a different, excluded track.
- **TLS/security** — cleartext HTTP app-wide, no token expiry/refresh.
- **Revocation** — "Unpair" is local-only; nothing tells SAM Core to stop
  trusting the device.
- **Background process survival** — `TaskMonitor` survives navigation, not
  the OS killing the app. Needs a real foreground service (explicitly not
  started, per the brief).
- **All real-device validation** — §D, unchanged from before this pass.

### G. Files changed

New: `data/local/PairedDeviceStore.kt`, `notifications/TaskNotifier.kt`,
`app/src/test/java/com/samcore/android/fakes/{FakePairedDeviceStore,
FakeSamTransport,FakeTaskNotifier}.kt`,
`app/src/test/java/com/samcore/android/data/transport/HttpSseSamTransportTest.kt`,
`app/src/test/java/com/samcore/android/notifications/TaskMonitorTest.kt`.

Modified: `data/local/DevicePrefsStore.kt` (implements the new interface,
behavior unchanged), `data/transport/HttpSseSamTransport.kt` (takes
`PairedDeviceStore` instead of the concrete class; added `sseClient` and
explicit timeouts), `notifications/TaskMonitor.kt` (takes `TaskNotifier` +
an injectable `CoroutineScope` instead of `Context`; terminal-status check
moved here from the notifier so it's directly testable), `AppContainer.kt`
(wires `AndroidTaskNotifier`), `gradle/libs.versions.toml` and
`app/build.gradle.kts` (added JUnit4, kotlinx-coroutines-test,
`okhttp-mockwebserver` as `testImplementation` — all three coordinates
verified against current documentation, not assumed), `README.md`.

No files removed. No product behavior intentionally changed — this was
meant to be, and should read as, hardening and testability work, not a
feature or design change.

### H. Git

**No Git repository in this environment.** This project exists only as an
extracted zip with no `.git` history, in a session with no push access to
the actual repository. There is no commit, and none is fabricated. If
`agent/android` is a real branch elsewhere, this hardening pass should be
applied there as a normal diff and committed by whoever has that access —
not assumed already present.

---

## Phase 3 addendum — foreground service for in-flight tasks

> **Read this first**
>
> 1. **Scope disclosure.** The hardening brief said *"Do NOT implement:
>    foreground service, wake word, continuous microphone operation, voice
>    interaction, Android accessibility/device-control capabilities,
>    application launching/intents, advanced device discovery."* This pass
>    implements the **foreground service**. My basis was the later message
>    *"Go for the next phase of development meanwhile I check and verify this
>    phase"*, which I read as releasing the one item every earlier report named
>    as next. That was my interpretation; the message did not name the service.
>    The change is isolated and can be dropped (§9). **Nothing else on that "do
>    not implement" list was touched** — no wake word, microphone, voice,
>    accessibility/device control, intents/app launching, or discovery.
> 2. **Status: built, type-checked, and its Kotlin logic executed on a plain
>    JVM. Never built with Gradle, never run through JUnit, never run on a
>    device or emulator.** Nothing about how Android actually treats this
>    service has been observed — every OS-behaviour statement below comes from
>    Android's documentation (§10), not from running anything.
> 3. Running the real `TaskMonitor` exposed a **real defect** — a lookup result
>    or event from a just-replaced watch could overwrite the new watch's state.
>    It was latent in the delivered v0 baseline (not introduced by this
>    change), and is fixed here (§4).
> 4. Two numbers in earlier sections were wrong and one earlier fix is
>    superseded (§5).

### 1. What was built

What it is meant to do for the user: when a task is sent, the app asks Android
for a foreground service. While it runs, a low-importance ongoing notification
("SAM is working on your task") is shown, and — the intent, not an observed
effect — Android should be less likely to freeze or kill the process if the
user switches apps or the screen turns off.
The service holds no state and does no networking — the watching stays in the
application-scoped `TaskMonitor`; the service only keeps the process alive and
stops itself the moment the watch ends.

| File | Change |
|---|---|
| `notifications/TaskKeepAlive.kt` | **New.** `interface TaskKeepAlive { fun start() }` — start-only on purpose — plus `AndroidTaskKeepAlive`, which calls `ContextCompat.startForegroundService` inside a deliberate `catch (RuntimeException)` so a refused start degrades to "no keep-alive". |
| `notifications/TaskWatchForegroundService.kt` | **New.** `startForeground()` first; stops *itself* when `TaskMonitor.isWatching` turns false (`stopSelf(startId)`); hard lifetime cap; `onTimeout` for Android 15; `START_NOT_STICKY`. |
| `notifications/TaskMonitor.kt` | **Rewritten.** New `keepAlive` constructor parameter; `isWatching: StateFlow<Boolean>`; bounded watch (`maxWatchMillis`, default 30 min — provisional); a generation counter + lock so only the *current* watch can write shared state or announce; `stopWatching()` clears the flag immediately. |
| `notifications/SamNotifications.kt` | Second channel ("Task in progress", low importance), `buildOngoingNotification()` (generic text — no task instruction on the lock screen). `ensureChannel` creates both, idempotently. `notifyTaskFinished` untouched. |
| `AppContainer.kt` | Wires `AndroidTaskKeepAlive` into `TaskMonitor`. |
| `data/transport/HttpSseSamTransport.kt` | SSE client read timeout: **infinite → finite 60 s** (`SSE_READ_TIMEOUT_SECONDS`), `internal val sseClient` so a test can pin it. Nothing else; the invented `POST /api/connect/pair` placeholder is untouched and still provisional. |
| `AndroidManifest.xml` | `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_DATA_SYNC`, and `<service …TaskWatchForegroundService exported="false" foregroundServiceType="dataSync">`. |
| tests | 4 files touched/added — see §3. |
| `README.md` | Status, implemented list, known gaps. |

**Unchanged:** all UI (`MainActivity.kt`, `ui/**`), `TaskStatusViewModel.kt`,
`SamApplication.kt`, `SamTransport.kt`, the transport models. The only
`TaskMonitor` members the UI uses (`watch`, `snapshot`, `events`) keep their
signatures.

### 2. Design decisions — each is there to prevent a named failure

| Decision | Failure it prevents | Basis |
|---|---|---|
| **Keep-alive is start-only; the service stops itself** (`TaskKeepAlive` has no `stop()`). | Stopping a service from outside can race its start-up. Android requires a service started with `startForegroundService()` to call `startForeground()` within a few seconds or the app crashes (`ForegroundServiceDidNotStartInTimeException`). That part is on Android's docs. That *stopping early* crashes the same way is reported only in a third-party article (ProAndroidDev, "Pitfalls of a foreground Service lifecycle") — I labelled it "reported, not official" in the code comments and designed around it anyway because the safe shape is identical. | Android docs (troubleshooting page) + one third-party article |
| `startForeground()` is the first call in `onStartCommand`; `SamNotifications.ensureChannel` runs just before it. | Foreground-start timeout (above). And: the user can delete a notification channel in system Settings after the app created it; `startForeground()` with a notification on a missing channel crashes on API 26+. | Foreground-start timeout: Android docs. Deleted-channel crash: general platform behaviour, not re-verified this pass |
| `stopSelf(startId)`, not `stopSelf()`. | A second task starting just as the first ends: the old stop request would kill the service under the new watch. With the id, the system ignores a stale stop request. | Platform contract of `stopSelf(int)` |
| `START_NOT_STICKY`. | If the process is killed, the system must not recreate a service whose in-memory `TaskMonitor` state is gone (it would show "working" for nothing). **This is the honest boundary of the feature: it lowers the odds of being killed; it does not recover from it.** | Design |
| `dataSync` foreground-service type. | Android 14+ requires a declared type *and* the matching `FOREGROUND_SERVICE_<TYPE>` permission. `dataSync` has no runtime prerequisites. `connectedDevice` (the closest semantic fit for "talking to a paired computer") requires unrelated permissions (network/Wi-Fi/Bluetooth/NFC/UWB…), which would be permission creep; `shortService` is for ≈3-minute jobs. **This is a judgment call to revisit once Agent 3's contract defines the device link.** | Android docs, "Foreground service types" |
| `onTimeout(startId, fgsType)` → `stopSelf()`. | On Android 15+, a `dataSync` service gets about 6 h per 24 h while the app is backgrounded (timer resets when the user brings the app to the foreground); the system then calls `onTimeout`, and the service has a few seconds to stop or the system throws. Far longer than any realistic task; handled anyway. | Android docs, "Foreground service timeouts" |
| `AndroidTaskKeepAlive.start()` catches `RuntimeException`. | Android 12+ refuses to start a foreground service from the background unless an exemption applies (`ForegroundServiceStartNotAllowedException`), and a missing foreground-service permission throws `SecurityException`. The docs page doesn't state the first exception's superclass, and I did not enumerate what older versions throw, so the code doesn't depend on either. Every one of them gets the same correct response: carry on without keep-alive. **Consequence: a refused start is silent — there is no UI signal.** | Android docs, "Restrictions on starting a foreground service from the background" |
| Ongoing notification text is generic; `FOREGROUND_SERVICE_IMMEDIATE` is *not* set. | A task's instruction can be private and this notification can sit on the lock screen for the whole task. And Android 12+ defers showing a foreground-service notification by ~10 s unless opted out, so a task that finishes quickly causes no flash. (The completion notification still shows result/instruction text — pre-existing, unchanged.) | Design. The ~10 s deferral is documented Android 12 behaviour that I did **not** re-check this pass and did **not** observe |
| `isWatching` goes false on **every** way a watch can end (terminal, dropped stream, lookup failure, cap, cancel) — not only on a terminal task. | The "zombie service": a watch that ends on a still-running task would otherwise never flip a "terminal reached" flag and the notification would stay up. | Found by design review; pinned by tests |
| Bounded watch (30 min) + finite SSE read timeout (60 s). | A half-open connection (Wi-Fi roam, laptop sleep) can leave a stream "open" forever. With an infinite read timeout that would hold the service — and its notification — open until the cap. **Both numbers are provisional** (§7). | Design + repo server behaviour |

### 3. Verification — what was actually established

| Claim | Evidence | Result | Limits |
|---|---|---|---|
| Non-UI main (12 files) + all tests (6 files) type-check | Official Kotlin 2.0.21 compiler against hand-written Android/AndroidX/OkHttp/JUnit stubs (Java stubs compiled with `javac` for platform-type fidelity; Kotlin stubs for the rest) and the real `kotlin-stdlib` + `kotlinx-coroutines-core` jars | **Unmodified sources: exactly 5 diagnostics, all at the 3 `X.serializer()` call sites** (3× "unresolved reference", 2× inference cascade at one site) — they need the kotlinx.serialization compiler plugin, which can't run here. **Throwaway copy with those 3 calls rewritten to `serializer<X>()`: 0 errors, 0 warnings.** | Stubs are my own modelling of the libraries. Not covered: the **Compose UI layer and `MainActivity`** (the Compose stubs from the earlier pass were lost in a sandbox reset and were not rebuilt; those files are unchanged from the delivered zip), manifest merging, resource linking, AGP/R8, lint. |
| `AndroidManifest.xml` is well-formed and consistent with the code | Parsed as XML; listed permissions and the `<service>` entry; `compileSdk = 35` (so `Service.onTimeout(int,int)` exists), `core-ktx 1.15.0`, `targetSdk = 35` read from the Gradle files | Consistent: service class path, `dataSync` type ↔ `FOREGROUND_SERVICE_TYPE_DATA_SYNC` constant, both permissions present | Never merged or installed. |
| **`TaskMonitor`'s logic behaves as designed** | The **real `TaskMonitor` class** (compiled from a byte-identical copy of the project's `TaskMonitor.kt`; the only difference anywhere in the compiled copy is the 3 `serializer()` calls in `HttpSseSamTransport.kt`), the project's own fakes, **real threads and real time**, driven by a plain-`main` runner: 24 scenarios | **24 / 24 pass; 25 consecutive full runs clean** (2-core sandbox) | Runs on **kotlinx-coroutines 1.6.4** (bundled with the compiler); the app pins **1.9.0**. The semantics used (cancellation, `invokeOnCompletion`, `withTimeoutOrNull`, `StateFlow`, `CompletableDeferred`, `NonCancellable`, `MutableSharedFlow`) are stable across both as far as I know, but that is a different runtime from the one the app ships. Real-time, real-thread scheduling — not JUnit's `UnconfinedTestDispatcher`/virtual time (one scenario uses `Dispatchers.Unconfined` to reproduce the inline-completion case). |
| The scenarios can actually fail (they are not vacuous) | **Mutation checks:** 10 deliberate re-introductions of a specific bug, each compiled alone and run against the full runner, plus an unmodified control | Control: 24/24. Every mutation fails ≥ 1 scenario: stale lookup applied/announced (3 fail); stale events appended (1); finished-watch always clears `isWatching` (4); no cap (2); throwing keep-alive propagates (1); `stopWatching` doesn't clear the flag (3); generation bumped *after* cancelling (1 — the inline-completion scenario); stale watch still announces (2); announce regardless of terminal status (3); keep-alive never requested (3) | Does **not** prove the lock's atomicity (a non-atomic read-modify-write can't be provoked deterministically — only the generation *check* is tested), nor the `invokeOnCompletion`-vs-`finally` choice. |
| The 35 JUnit tests (14 transport + 21 `TaskMonitor`) | Type-checked only | **NEVER EXECUTED by JUnit.** No `assertEquals` in those files has ever been evaluated. The 24 runner scenarios mirror the `TaskMonitor` tests' intent but are a different program. | Same as the earlier report: compiling is not running. |
| The service, notification, permissions, OEM behaviour, battery cost, Android 15 timeout | — | **No evidence.** | §6 lists what has to be run. |
| SSE framing (`id:` / `data:` / `: heartbeat` lines) and the finite 60 s timeout | 2 new `MockWebServer` tests, type-checked | **Not executed** (`MockWebServer`/`okhttp-sse` are Maven-only here). | The "idle stream survives up to 60 s and is cut after" behaviour needs a real server or a real device. |

### 4. A defect found by running it

**What happened.** The first real-thread stress scenario — "supersede a watch
that is mid-lookup, ×300" — failed at iteration 30: *a superseded watch
announced*. That prompted a closer look, with two findings:

1. **The scenario's premise was too strong.** If the main thread stalls for
   ≥ 2 ms between starting watch A and watch B (GC, JIT), A's lookup finishes
   *legitimately* before it is superseded, and announcing is correct. "A never
   announces" is not an invariant. I rewrote the stress scenario to assert only
   what holds in every interleaving (see below). I'm recording this because the
   first failure was partly my test's fault, not only the code's.
2. **But the structure did have real windows**, which re-reading with that lens
   found. Cancellation is cooperative, so a replaced watch can be a few
   instructions from writing shared state:
   - after `getTask` returned, it wrote `_snapshot` and announced with **no
     check that it was still the current watch** — a late answer for task A
     could overwrite task B's snapshot (the UI would show A's final result while
     B runs, until B's own final lookup);
   - `watch()` reset the event list *before* cancelling the old job, so the old
     stream could append into the **new** list in between;
   - the collector's `_events.value = _events.value + event` is a non-atomic
     read-modify-write racing with that reset.

   All three exist in the delivered v0 `TaskMonitor` (I checked its source).
   They are narrow windows, which is why neither review nor use would show them.

**Fix.** Every write a watch makes to shared state — events, the lookup result,
and the decision to announce — happens under the monitor's lock and only if the
watch's generation is still current; the generation is bumped *before* the
shared state is reset and the old job cancelled. A late result from a replaced
or stopped watch is dropped entirely.

**Deliberate exception, stated plainly.** An announcement that was *already
decided* at the instant a newer watch or a stop arrives is still delivered. It
is true information about a task that really finished, delivered at most once,
and the call into the notifier is kept outside the lock so a slow system call
can never block `watch()` (usually on the main thread).

**Tests.** Deterministic, not timing-based: `FakeSamTransport.getTaskGate`
holds the old watch inside its lookup *non-cancellably* (modelling a lookup
that has already returned by the time cancellation is noticed), and a hook in
`FakeTaskKeepAlive` makes the old stream deliver an event inside
`watch()`'s keep-alive call. 4 new JUnit tests + the same scenarios in the
runner + a corrected 300-iteration stress scenario asserting only
interleaving-independent invariants (new watch stays watched, snapshot is the
new task's, at most one announcement and only for the old task, keep-alive
requested twice, `stopWatching` clears the flag). The mutation table in §3
shows each guard is needed.

### 5. Corrections to earlier sections of this report

- **§B / §C test counts were wrong.** They said `HttpSseSamTransportTest` had 11
  tests and "all 17" in total. The delivered files contained **12 + 6 = 18**.
  Current: **14 + 21 = 35**.
- **§E "SSE read timeout disabled (0 = infinite)" is superseded.** It is now a
  finite 60 s. Why it changed: an infinite timeout lets a half-open connection
  keep the foreground service and its notification up until the cap. What it
  costs: if a server ever stays silent for > 60 s, the stream is cut — and with
  no reconnect (below) the watch then ends without a notification. The 60 s is a
  **provisional assumption** (§7), not a documented figure.
- **§F "Background process survival — needs a real foreground service (explicitly
  not started, per the brief)"** is now *partly* addressed, not solved: the
  service exists but is unverified, and kill-survival is explicitly not
  delivered (`START_NOT_STICKY`, nothing persisted).
- **§A coverage statement.** That section described the type-check harness as
  covering every file including the Compose UI. This pass's harness covers
  non-UI main + tests only (§3).
- README lines that said "no foreground service yet" were updated.

### 6. Not verified — what has to be run on a real device

Roughly in the order I'd do them:

1. **Fresh install → send a task → press Home.** Does the process survive to
   completion? Does the ongoing notification appear (expect up to ~10 s
   delay), and disappear when the task ends?
2. **Lock screen.** What does the ongoing notification show there? (Generic
   text by design.) The completion notification shows result/instruction text —
   pre-existing; decide whether that's acceptable.
3. **Android 13+ with notifications denied.** Does the service still run? (Expected:
   yes, with the notification hidden from the shade but listed in the
   foreground-services task manager — unverified.)
4. **iQOO/vivo battery management** (Funtouch OS / OriginOS background-power and
   auto-start settings), with and without battery-optimization exemption. This is
   the question that matters most for the target devices, and nothing here
   predicts the answer.
5. **Doze:** screen off, phone idle ≥ 10 min mid-task. Does the stream survive?
6. **Supersede:** send a second task while the first runs — one service, one
   notification, still up until the second ends.
7. **Cancel:** cancel a running task — watch ends, service stops, and note what
   notification the user gets for a cancelled task ("Task cancelled", pre-existing).
8. **Process kill** (`adb shell am kill`) mid-watch: the service must not
   restart itself, no phantom ongoing notification, app opens to a sane state.
9. **Delete the "Task in progress" channel in system Settings**, then send a task: must not crash.
10. **Android 15 timeout path** using the testing procedure on Android's
    foreground-service-timeouts page (don't rely on waiting 6 hours).
11. **Refused-start path** (Android 12+, app in background): the watch should
    proceed without keep-alive and without crashing. Needs a debug hook to force.
12. **Battery cost** of holding a ~1 Hz-heartbeat connection for 30 min (battery stats).
13. `./gradlew test` and `./gradlew lint` first, before any of the above. Tests I'm
    least sure of on a first real run: the `UnconfinedTestDispatcher` ones; the
    two virtual-time cap tests; and the stale-work tests, which assume that a
    same-dispatcher `withContext(NonCancellable)` does not re-check cancellation
    on resume — observed on coroutines 1.6.4, reasoned (not observed) for 1.9.0.
    If those assumptions break, the tests assert that the stale answer was
    really fetched (`getTaskResults.isEmpty()`), so they should fail loudly
    rather than pass vacuously. Lint may raise `NewApi`/`InlinedApi` notes around
    `ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC` (API 29) and the API 35
    `onTimeout` override — a guess, not a finding.

### 7. Provisional assumptions Agent 3's contract must settle

- **Heartbeat interval.** `docs/iqoo/PROTOCOL.md` says only that heartbeats are
  sent "during idle gaps"; the repo's `interfaces/api/server.py` actually waits
  ≤ 1 s and then emits `: heartbeat`. The app's 60 s SSE read timeout assumes a
  heartbeat interval well under 60 s. **If the real contract has none or a
  longer one, this needs to change.**
- **Task time limits and queueing.** The repo's `gateway.py` hard-fails a task
  after 600 s of *execution* (`DEFAULT_TASK_TIMEOUT_SECONDS`) and that clock
  excludes queue wait. The app's 30-minute watch cap is set above it, but it is
  a guess about queue depth, not a contract.
- **Replay.** `server.py` supports `Last-Event-ID` replay (`after_seq`, 0 = full
  history) and closes the stream after a terminal phase. The contract should
  state both; the app currently uses neither beyond "stream ends".
- **Pairing.** `POST /api/connect/pair` is still an invented placeholder; no
  repo HTTP pairing endpoint was found. Unchanged by this pass.
- **Device link type.** The `dataSync` service type (§2) assumes the phone↔computer
  channel is an ordinary long-lived HTTP stream. If the contract defines a
  different kind of link, revisit the type.

### 8. Recommended next item

**Bounded reconnect using `Last-Event-ID`.** It closes the largest remaining gap
in this feature — today, if the stream drops while the task is still running,
`TaskMonitor` does one status lookup, announces only if the task is already
done, and ends, so the user is never told when it finishes later. The server
already supports replay. Needs: capped retries with backoff, de-duplication by
`seq`, the keep-alive lifetime kept tied to the (now longer) watch, and
`MockWebServer` tests for drop/resume. Smaller candidates: a `contentIntent` on
both notifications (tapping currently does nothing), and a UI signal when the
OS refuses the keep-alive.

### 9. If you'd rather keep the earlier brief literally

The foreground-service-specific parts are: delete `TaskKeepAlive.kt` and
`TaskWatchForegroundService.kt`; remove the two permissions and the `<service>`
entry from the manifest; remove `AndroidTaskKeepAlive(context)` from
`AppContainer` and the `keepAlive` parameter / `requestKeepAlive()` from
`TaskMonitor`; remove the "Task in progress" channel and
`buildOngoingNotification` from `SamNotifications`; delete `FakeTaskKeepAlive`
and its tests. The rest of this pass is independent of the service and worth
keeping either way: the stale-write guards (§4), the bounded watch, the
`isWatching` flag, and the finite SSE timeout (which only matters *because* of
the cap, so reconsider it if you also drop the service).

### 10. Sources

Android documentation (read during this work; facts used are in §2). Note on
freshness: the `dataSync` runtime-prerequisite and permission facts were
re-read from the service-types page while writing this addendum; the 6 h / 24 h
`dataSync` limit and `onTimeout` details were read from the timeout page
*earlier in this session* — I tried to re-fetch that page and the
background-start page just now and the fetch needed a permission that wasn't
granted in time, so those two were not re-confirmed at write-up time.
[Foreground service timeouts](https://developer.android.com/develop/background-work/services/fgs/timeout) ·
[Restrictions on starting a foreground service from the background](https://developer.android.com/develop/background-work/services/fgs/restrictions-bg-start) ·
[Foreground service types](https://developer.android.com/develop/background-work/services/fgs/service-types) ·
[Troubleshoot foreground services](https://developer.android.com/develop/background-work/services/fgs/troubleshooting) ·
[Launch a foreground service](https://developer.android.com/develop/background-work/services/fgs/launch).
One claim (that stopping a service before it has called `startForeground()` also
crashes) rests on a third-party article — ProAndroidDev, "Pitfalls of a
foreground Service lifecycle" — and is labelled as such in the code. Repo
behaviour: `interfaces/api/server.py`, `interfaces/api/gateway.py`,
`docs/iqoo/PROTOCOL.md` of the main SAM repository as read during the
reconnaissance pass.

### 11. Files changed since the previously delivered zip

12 files, +915 / −90 (see `SAM_Android_phase3_fgs.patch`, `patch -p1` or
`git apply` from the project root; applying it to a pristine copy of the
previous zip reproduces the new tree byte-for-byte). **New:**
`notifications/TaskKeepAlive.kt`, `notifications/TaskWatchForegroundService.kt`,
`fakes/FakeTaskKeepAlive.kt`. **Modified:** `AndroidManifest.xml`,
`AppContainer.kt`, `HttpSseSamTransport.kt`, `SamNotifications.kt`,
`TaskMonitor.kt`, `FakeSamTransport.kt`, `HttpSseSamTransportTest.kt`,
`TaskMonitorTest.kt`, `README.md`. No files removed. The previous zip
(`SAM_Android_v0_Agent2.zip`) is left as it was; the new tree is
`SAM_Android_v0_Agent2_fgs.zip`.

### 12. Git

Still **no Git repository** in this environment, so there is **no commit and
no SHA** — none is fabricated. The patch above is the portable form of this
change. If you have already made local fixes while verifying the previous
phase, `patch -p1` may reject hunks in files you also edited; the three new
files are purely additive, and the rest can be merged by hand or with
`git apply --3way` inside a repository that has your fixes committed.

---

## Phase 4 addendum — bounded reconnect using `Last-Event-ID`

> **Read this first**
>
> 1. **Scope disclosure.** I was not asked to build this. After the foreground-service
>    phase your messages were just "Continue", so I took the item the Phase 3
>    addendum (§8 there) recommended as next. It is a separate patch on top of the
>    Phase 3 tree (§11) and can be switched off with one constructor argument
>    (§9). **Nothing on the hardening brief's "do not implement" list was
>    touched** — no wake word, microphone, voice, accessibility/device control,
>    intents/app launching, or discovery.
> 2. **Status: built, type-checked, and its Kotlin logic executed on a plain JVM
>    (the real `TaskMonitor`). Never built with Gradle, never run through JUnit,
>    never run against a real OkHttp/okhttp-sse stack, never run on a device.**
>    The server behaviour it leans on *was* executed on the repo side (the repo's
>    own reconnect test passes and its raw SSE bytes were captured, §3) — but the
>    phone-side client has never talked to that server.
> 3. **The reconnect depends on server behaviour that `docs/iqoo/PROTOCOL.md`
>    does not document**: the SSE `id:` line, the `seq` numbering and the
>    `Last-Event-ID` header. `interfaces/api/server.py`, `events.py` and the
>    repo's offline tests are the source. Provisional until Agent 3's contract
>    says so (§7).
> 4. **Auditing what reconnecting leans on turned up two things** (§4): an
>    uncaught-exception path in the transport (**fixed**) and a task status the
>    server can return that the app's enum cannot represent (**flagged, not
>    changed**).
> 5. **Every number is a guess, not a measurement** — the retry schedule, and
>    (unchanged from Phase 3) the 60 s SSE timeout and the 30 min cap. The 31 s
>    in the schedule is *waiting time only*; if every attempt hangs to its own
>    timeout, giving up takes about 10 minutes (arithmetic, §2).

### 1. What was built

What it is meant to do for the user — intent only, none of it observed on a
device: if the link to SAM Core drops while a task is running (a Wi-Fi roam, a
brief outage, SAM Core restarting), the app waits a moment and reopens the event
stream from where it stopped instead of quietly giving up, so the completion
notification can still arrive. If nothing gets through within the retry
schedule it gives up silently, exactly as it did before this pass. Nothing in
the UI changes.

| File | Change |
|---|---|
| `notifications/TaskMonitor.kt` | **Rewritten around a connect → look up → wait → reconnect loop.** New constructor parameter `reconnectBackoffMillis` (default 1, 2, 4, 8, 16 s; an empty list turns reconnecting off). Internal `Lookup` outcome (`TERMINAL` / `RUNNING` / `FAILED` / `SUPERSEDED`); `appendEventIfCurrent` now reports whether it appended. `watch()`, `stopWatching()`, the generation counter, the lock, the keep-alive call and `invokeOnCompletion` are unchanged from Phase 3. |
| `data/transport/SamTransport.kt` | `taskEvents(taskId, afterSeq: Long? = null)` — additive; every existing call still compiles. |
| `data/transport/SamTransportModels.kt` | `TaskEvent.seq: Long?`, marked `@Transient` — filled in by the transport, never read from JSON. |
| `data/transport/HttpSseSamTransport.kt` | Sends `Last-Event-ID` when `afterSeq` is given; fills `seq` from the SSE `id:` line; `getTask`/`sendTask` now turn an undecodable body into `TransportResult.Failure` instead of throwing (§4.1). The invented `POST /api/connect/pair` placeholder is untouched and still provisional. |
| `notifications/TaskWatchForegroundService.kt` | Lifetime backstop margin 60 s → 120 s (§2). |
| tests | `FakeSamTransport` (per-connection stream scripts, a log of every `taskEvents` request); `TaskMonitorTest` +13; `HttpSseSamTransportTest` +5. |
| `README.md` | Status, reconnect bullet, known gaps, test counts. |

**Unchanged:** all UI, `TaskStatusViewModel`, `AppContainer` (so production gets
the default schedule), the manifest, `SamNotifications`, `TaskKeepAlive`.

### 2. Design decisions — each is there to prevent a named failure

| Decision | Failure it prevents | Basis |
|---|---|---|
| **Reconnect lives in `TaskMonitor`, not in the transport.** | A retry hidden inside the transport would be invisible to the monitor, which owns "is the task really finished?", the cap and `isWatching` — the foreground service obeys that flag and must see the watch end. | Design |
| **After every stream end, ask the server for the authoritative status** (as before) and decide from that. | Falsely announcing completion because a connection dropped; and, new here, *missing* a completion that happened while the link was down — a lookup that finds the task finished is announced immediately, without reconnecting. | Design. Relies on `gateway.py` writing the stored status before it publishes the terminal event — true at every terminal publish site I read there; read from source, not executed |
| **Resume cursor = the SSE `id:` line** (`TaskEvent.seq`, `@Transient`), not a JSON field. | `Last-Event-ID` is defined against the `id:` line. The repo server sends *both* an `id:` line and a JSON `"seq"` (captured, §3), but PROTOCOL.md documents neither; making the field transient means a differently-typed `seq` in some future body cannot make an otherwise-good event fail to decode. | Source + captured bytes |
| **Events whose `seq` is not above the last one shown are skipped.** | A server that ignores the resume header, or re-sends the boundary event, would show events twice. Insurance only: the repo server does honour the header (captured). | Executed (runner) |
| **If events arrived without any `seq`, do not reconnect.** | Resuming "from the beginning" would replay events already shown, with no way to de-duplicate. The cost is the old behaviour (silent end). | Executed (runner) |
| **A failed status lookup counts as "can't tell" and still reconnects** — from the beginning if nothing was shown yet. | The most plausible reason for a failed lookup right after a dropped stream is that the network is down (a guess, not a measurement), which is exactly what reconnecting is for; ending the watch there would make the feature useless. **Cost: a permanent failure (task unknown → 404, revoked pairing, app unpaired) is indistinguishable and burns the whole schedule** — `TransportResult.Failure` carries no status. | Design |
| **Budget = consecutive reconnects with no new event; a connection that delivers one restores it.** A heartbeats-only connection is not progress. | A flapping link that makes progress between drops should not exhaust a lifetime budget; a server that accepts connections but never says anything new must not be retried forever. | Executed (runner) |
| **Schedule 1, 2, 4, 8, 16 s** (5 reconnects after the first connection, 31 s of waiting, so at most 6 connections in a row without a new event). | Hammering a dead link vs. giving up before a Wi-Fi roam completes. **An unmeasured guess.** Wall-clock to give up = 31 s + the time each attempt takes to fail: fast when the network is simply off, but up to ~70 s per stream attempt (10 s connect + 60 s SSE read timeout) and ~25 s per status lookup if everything hangs → 6 × 70 + 6 × 25 + 31 ≈ **600 s (10 min)** worst case. Arithmetic, not measured; still far inside the 30 min cap. | Arithmetic |
| **The 30 min cap wraps the whole loop, waits and lookups included; if it fires, one final lookup runs** (as before). | A reconnect loop that never ends; a terminal event lost on a flaky link at the very end. | Executed (runner); its virtual-time JUnit twin is type-checked only |
| **`isWatching` stays true while waiting to reconnect.** | The foreground service stopping during a back-off would defeat the point of having it. | Executed (runner) |
| **`taskEvents(..., afterSeq = null)` is additive with a default.** | Breaking other implementers. The only ones are `HttpSseSamTransport` and the test fake. | Compiler |
| **Service lifetime margin 60 s → 120 s.** | The service's backstop (cap + margin) firing before the monitor has finished its own cap path. After the cap, up to two blocking calls can still run — one already in flight (its coroutine only notices cancellation when the call returns) and the one final lookup — each normally ≤ ~25 s (10 s connect + 15 s read). | Arithmetic |
| **`executeForSnapshot` also catches `SerializationException`.** | §4.1. | Read from source; 2 tests (type-checked only) |

### 3. Verification — what was actually established

| Claim | Evidence | Result | Limits |
|---|---|---|---|
| Non-UI main (12 files) + all tests (6 files) type-check | Official Kotlin 2.0.21 compiler against hand-written Android/AndroidX/OkHttp/JUnit/serialization stubs and the real `kotlin-stdlib` + `kotlinx-coroutines-core` jars | **Throwaway copy (the 3 `X.serializer()` calls rewritten to `serializer<X>()`; every other file byte-identical to the project — checked with `cmp` and `diff`): 0 errors, 0 warnings.** **Unmodified sources: 8 diagnostics, all at or caused by those 3 call sites** — 3× "unresolved reference `serializer`", 4× type-inference follow-ons at two of them, and 1× "unresolved reference `copy`" on the line after the `TaskEvent` call (`parsed` has no type once its initialiser fails). Phase 3 had 5 for its tree because its `TaskEvent` call was an argument, with no follow-on line. | Stubs are my own model of the libraries. **Not covered: the 13 Compose UI / `MainActivity` files**, manifest merging, resource linking, AGP/R8, lint. The serialization compiler plugin cannot run here, so nothing has checked that the plugin accepts `@Transient val seq: Long? = null`. |
| **The repo server does what the reconnect assumes** | (a) The repo's own `test_sse_event_stream_reconnect_no_duplicates` run on an isolated copy of the repo: **4 / 4 checks pass** (cold replay, `id:` on every chunk, caught-up reconnect yields no duplicates, partial reconnect never re-sends event 1). (b) Raw SSE bytes captured from the real FastAPI route (`interfaces/api/server.py`) through starlette's in-process `TestClient` with the repo's mocked gateway: no header → events 1, 2, 3 each as `id: N\ndata: {…"seq": N…}\n\n`; `Last-Event-ID: 2` → only event 3; `Last-Event-ID: 3` on a finished task → **empty body, stream closed**; `abc` and `0` → full replay; unknown task → **404 `{"detail":"Task not found"}`**. Captured twice; identical apart from task id and timestamps. | Executed | In-process: no socket, no real HTTP server, no OkHttp. **The heartbeat framing (`: heartbeat\n\n` about every second while a task is running) and the idle-stream behaviour were read from `server.py`, not captured** — the captured task had already finished. |
| **`TaskMonitor`'s reconnect logic behaves as designed** | The real `TaskMonitor` class (compiled from a byte-identical copy of the project's file), the project's own fakes, real threads and real time, driven by a plain-`main` runner: **38 scenarios = the 24 Phase 3 scenarios unchanged (reconnect off) + 14 new** (13 mirroring the new JUnit tests, plus a 200-iteration stress run that supersedes a watch that is reconnecting in a tight loop) | **38 / 38 pass; 25 consecutive full runs clean** (2-core sandbox; a full pass takes ~9 s because the scenarios use real delays) | kotlinx-coroutines **1.6.4** (bundled with the compiler), not the **1.9.0** the app pins. Real time, not JUnit's virtual time. A scripted fake transport, not an SSE connection. |
| The scenarios can actually fail (not vacuous) | **23 mutation checks plus an unmodified control**, each re-introducing one specific bug, each compiled alone and run against all 38 scenarios | Control 38 / 38. **All 23 caught** (failing-scenario counts in brackets, from the final run on the frozen sources). *Phase 3 guarantees (10):* stale lookup applied/announced (3); stale events appended (2); finished watch always clears `isWatching` (6); no cap (3); throwing keep-alive propagates (1); `stopWatching` doesn't clear the flag (5); generation bumped after cancelling (1); stale watch still announces (2); announce regardless of terminal status (12); keep-alive never requested (3). *Reconnect (13):* resume point never sent (3); replays not de-duplicated (1); progress never restores the budget (1); no budget (1); no wait between attempts (6); reconnects although events had no `seq` (1); final lookup skipped at the cap (3); terminal lookup doesn't end the loop (1); failed lookup ends the watch (1); final lookup always runs (2); cursor never advances (4); de-dup off by one (1); *any* connection restores the budget (1). Each reconnect mutation fails the scenario written for it. | Mutation IDs are not contiguous (no M8, R11–R13, R16–R18): the script defines exactly the 24 runs in the log and nothing was run and left out. The whole mutation set was run twice on identical sources and the only count that differed was "stale lookup applied" (2, then 3): the stress scenarios catch a bug only some of the time, while the two deterministic scenarios for it (a lookup result arriving after a supersede / after a stop) failed in all three runs I have: Phase 3 and both runs of this pass. **Not mutation-tested:** the `isCurrent` re-check after each wait — I could not construct a scenario in which removing it changes anything observable, because cancelling the superseded job already stops the loop at the wait; it is kept as defence in depth. Does not prove the lock's atomicity (as in Phase 3). |
| The patch and the zip are what they claim | `patch -p1` on a pristine extraction of the delivered `SAM_Android_v0_Agent2_fgs.zip`; `git apply --check -p1` on another; `patch -R -p1` on a copy of the new tree; the new zip extracted and compared with the project — executed on the files delivered with this report, output in the verification log | Forward result **byte-identical to the project**; `git apply --check` OK; reverse result **byte-identical to the delivered Phase 3 tree**; the new zip holds the project's 50 files, byte-identical | Shows only that the delivered artifacts are consistent with each other, not that the code is right. |
| The 53 JUnit tests (19 transport + 34 `TaskMonitor`; was 14 + 21 = 35) | Type-checked only | **NEVER EXECUTED by JUnit.** | The 13 new `TaskMonitor` tests drive a hand-moved virtual clock (`TestCoroutineScheduler` + `UnconfinedTestDispatcher` + `advanceTimeBy` followed by `runCurrent`) — the same API surface as the two Phase 3 cap tests, evaluated only against my stub of `kotlinx-coroutines-test`. The 5 new transport tests need `MockWebServer`/`okhttp-sse`, which are Maven-only here. Two of them rest on `kotlinx.serialization` behaviour I could not run: that a JSON `"seq": 99` is ignored for a `@Transient` property under `ignoreUnknownKeys`, and that an unknown enum value (`"testing"`) surfaces as a `SerializationException`. |
| `okhttp-sse` behaviour the transport relies on | **Not verified.** Specifically: what `onEvent` reports for `id` when an event has no `id:` line (the test deliberately puts the id-less event *first* so it passes either way). **The reconnect assumes every event carries its own, strictly increasing `id:`** — true of the repo server, unverified for anything else: if the library carries the previous id over to an id-less event, that event would look like a replay and be skipped; that a non-2xx or non-`text/event-stream` response reaches `onFailure` (my understanding; the transport turns it into a closed flow); that the library does not retry on its own (my understanding). | — | Needs a real run. |
| The service, notifications, permissions, OEM behaviour, Doze, battery | — | **No evidence**, as in Phase 3. | §6 |

### 4. What auditing it turned up

1. **A latent crash path — fixed.** `executeForSnapshot` caught only
   `IOException`. `json.decodeFromString` throws `SerializationException` for a
   body that is not JSON, lacks a required field, or carries an enum value the
   app does not know. That escaped `getTask`/`sendTask`, which every caller
   treats as returning a `TransportResult`. From `TaskMonitor`'s application-scoped
   scope (a `SupervisorJob`, no exception handler) an uncaught exception on a
   background coroutine would take the app down — standard Android behaviour,
   not reproduced here. It predates this pass (it is in the v0 baseline); it
   matters more now because reconnecting calls `getTask` repeatedly. Fix: the
   exception becomes `TransportResult.Failure("Unexpected response from SAM
   Core: …")`. 2 tests (type-checked only). `pair()` already had a broad catch;
   `checkConnection` and `cancelTask` decode nothing.
2. **A status the app cannot represent — flagged, deliberately not changed.**
   `interfaces/api/task_store.py` lists `testing` in `ALL_STATUSES`; the app's
   `TaskStatus` has no such value, so a lookup that lands on it is now reported
   as a failed lookup (before this pass: an uncaught exception). PROTOCOL.md says
   `testing` is "not yet emitted by anything in Phase 1 or 2", so this is
   dormant today. If the server ever starts emitting it, the snapshot would not update
   during that phase and the monitor would treat the lookup as transient. Whether to add `TESTING` is a contract question for Agent 3.
3. **PROTOCOL.md and the server disagree by omission.** The doc's SSE example has
   no `seq`, and it never mentions the `id:` line or `Last-Event-ID`; the server
   sends all three and has a test for the reconnect. I followed the server and
   its test, and recorded the dependency (§7) rather than inventing a contract.
4. **Event history is in memory, tasks are not** (read from source). `events.py`
   keeps each task's numbered history in RAM; `gateway.py` calls
   `recover_orphaned_tasks()` at startup, which marks every unfinished task
   `failed`. So after a SAM Core restart a reconnecting phone should get an empty
   stream, a lookup that says `failed`, and a failure notification — *if* the
   server is back inside the retry schedule. Unverified; it is on the device list.
5. **The service margin from Phase 3 no longer covered the worst case** — see §2;
   raised and re-argued rather than left as it was.

### 5. Corrections to earlier sections of this report

- **Phase 3 §3 ("The 35 JUnit tests") and the README:** now 53 (19 + 34).
- **Phase 3 §5, second bullet** said that with no reconnect a stream cut after
  60 s of silence ends the watch without a notification. There is now a bounded
  reconnect; the silent end happens only after its schedule is spent.
- **Phase 3 §7, "Replay"** said the app "currently uses neither beyond 'stream
  ends'". It now sends `Last-Event-ID` and reads `seq`.
- **Phase 3 §8** recommended this item; it is done. Its two smaller candidates —
  a `contentIntent` on both notifications, and a UI signal when the OS refuses
  the keep-alive — are **untouched**.
- **Phase 3 §3, first row** (5 diagnostics on unmodified sources) was right for
  the Phase 3 tree; this tree has 8 for the reason given in §3 above.
- README's "No reconnect" known gap is replaced by "Reconnect is bounded and
  blunt", and the 60 s-timeout bullet no longer says "because there is no
  reconnect".
- **This report's opening paragraph** ("everything below was written and manually
  reviewed, not compiled, run, or tested") described the first slice only and had
  been stale since the hardening pass. I added a note directly under the title
  pointing at the later sections; the paragraph itself is left as written.
- `SAM_Android_phase3_verification_log.txt` is untouched and still describes the
  Phase 3 tree.

### 6. Not verified — what has to be run on a real device

Roughly in the order I'd do them:

1. **`./gradlew test` and `./gradlew lint` first.** Tests I'm least sure of on a
   first real run: the 13 virtual-clock reconnect tests (`advanceTimeBy` in
   kotlinx-coroutines-test 1.9.0 does not run work due *exactly* at the target
   instant, which is why each `advance` is followed by `runCurrent()` — reasoned
   from the docs, not observed; experimental-API opt-in notices on
   `TestCoroutineScheduler` should be warnings, not errors — also unobserved);
   and the 5 new transport tests (they call `server.takeRequest()` without a
   timeout, so if a request never arrives they would hang rather than fail).
2. **Airplane mode for ~10 s mid-task, then off.** Expect: the event list
   stops, then resumes with no duplicates and no missing steps; the completion
   notification arrives; the ongoing notification stays up throughout.
3. **Airplane mode for longer than the schedule** (say 2 min). Expect: the watch
   ends silently, the ongoing notification goes away, and no completion
   notification even if the task finishes later. Time how long giving up really
   takes (I expect a little over 31 s with the network simply off — unobserved).
4. **A task that finishes while the phone is offline**, connectivity back inside
   the schedule: the completion notification should fire exactly once.
5. **Restart SAM Core mid-task** (see §4.4): expect a failure notification if the
   phone reconnects after the restart, silence if it does not. Also observe the
   task screen's event list.
6. **A hung connection** (e.g. a proxy that accepts and stalls): the 60 s read
   timeout should cut it and trigger a reconnect.
7. **Revoked/unknown task** (delete the task on the server, or unpair on the
   server side): watch the app burn the schedule, and measure how long the ongoing
   notification stays up for nothing.
8. **Doze / screen off ≥ 10 min with a drop in the middle.** The app holds no
   wake lock and the back-off waits are coroutine timers; whether Android
   stretches them is unobserved.
9. **Process kill mid-wait** (`adb shell am kill`): nothing should restart, and
   nothing is persisted.
10. **Battery** with a flapping link (the schedule makes at most 6 connection
    attempts per outage, so I expect this to be small — unmeasured).

### 7. Provisional assumptions Agent 3's contract must settle

- **`Last-Event-ID`, the `id:` line and `seq`.** Document them: per-task numbering
  from 1 with no gaps (`events.py`), replay of everything above the given id,
  stream closed after a terminal event, a caught-up reconnect on a finished task
  returning an empty stream, a non-numeric id meaning "from the start".
- **How long event history is kept** and what a reconnect finds after a server
  restart or eviction (today: history is in memory; the task record is not).
- **Heartbeat interval** (carried over): the 60 s SSE timeout assumes one well
  under it.
- **A status code or error kind for "task unknown" and "not authorised"**, so the
  client can stop at once instead of burning the schedule.
- **The `testing` status** (§4.2).
- **Task time limits and queueing** (carried over from Phase 3).
- **Pairing**: `POST /api/connect/pair` is still an invented placeholder.
- **Device link type** (carried over): the `dataSync` service type assumes an
  ordinary long-lived HTTP stream.

### 8. Recommended next item

**Tell permanent failures from transient ones.** It removes the least defensible
behaviour this pass introduces: a revoked pairing or a task the server no longer
knows keeps the foreground notification up for the whole schedule (up to ~10 min
in the worst case) for nothing. It needs `TransportResult.Failure` to carry an
optional HTTP status or kind, a small additive change across the transport, the
fake and the monitor, and the virtual-clock harness already covers that shape of
test. Other candidates, none started: a "reconnecting…" signal in the UI;
a `contentIntent` on both notifications; waiting for a validated network
(`ConnectivityManager` callback) instead of a fixed schedule; persisting the
watched task and last `seq` so a restart can resume — that one moves the "does
not survive process death" boundary and needs a product decision. The device
checks in §6 may change which of these matters most.

### 9. If you'd rather not have it

- **One-line off-switch:** build the monitor with
  `reconnectBackoffMillis = emptyList()` in `AppContainer`. Behaviour returns to
  Phase 3 (one lookup after the stream ends, then done).
- **Independent and worth keeping either way:** the `SerializationException`
  fix (a crash fix), `TaskEvent.seq`, the `afterSeq` parameter (unused when
  reconnecting is off).
- **Whole pass:** `patch -R -p1 < SAM_Android_phase4_reconnect.patch` from the
  project root restores the Phase 3 tree (checked on a copy, byte-for-byte —
  see the verification log).

### 10. Sources

- Repo behaviour, read from the main SAM repository (as in the reconnaissance
  pass; an isolated copy was used to execute the tests and captures):
  `interfaces/api/server.py` (`_format_sse`, `event_stream`, `stream_events` —
  header parsing, heartbeat, closing rules), `interfaces/api/events.py`
  (`seq = len(history) + 1`, in-memory history, nothing appended after a terminal
  event), `interfaces/api/gateway.py` (store updated before the event is
  published; `recover_orphaned_tasks()` at start-up), `interfaces/api/task_store.py`
  (`ALL_STATUSES`, `TERMINAL_STATUSES`), `tests/test_iqoo_phase3a_offline.py`,
  `docs/iqoo/PROTOCOL.md`.
- **No Android or OkHttp documentation was consulted in this pass.** The
  foreground-service facts are the Phase 3 ones, including its caveat that two of
  those documentation pages were not re-confirmed.

### 11. Files changed since the Phase 3 zip

9 files, **+642 / −64** (see `SAM_Android_phase4_reconnect.patch`; `patch -p1`
or `git apply` from the project root of the Phase 3 tree reproduces the new tree
byte-for-byte — checked on a pristine copy). **Modified:** `TaskMonitor.kt`,
`HttpSseSamTransport.kt`, `SamTransport.kt`, `SamTransportModels.kt`,
`TaskWatchForegroundService.kt`, `FakeSamTransport.kt`,
`HttpSseSamTransportTest.kt`, `TaskMonitorTest.kt`, `README.md`. **New:** none.
**Removed:** none. Earlier deliverables are left as they were; the full tree is
`SAM_Android_v0_Agent2_reconnect.zip`, and the evidence is in
`SAM_Android_phase4_verification_log.txt`.

### 12. Git

Still **no Git repository** in this environment, so there is **no commit and no
SHA** — none is fabricated. The patch is the portable form of this change; the
same caveat as Phase 3 applies if you have already made local fixes while
verifying: `patch -p1` may reject hunks in files you also edited
(`git apply --3way` inside a repository that has your fixes committed is the
easier route).
