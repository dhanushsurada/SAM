# Hands / Desktop-Control Reliability Reform (Phase 3) — Root Causes From Real Testing

Status: ready to commit and test on the Mac. Seven real gaps fixed across
four files, all found by reading the actual code end to end — not
guessed — and cross-checked against what Phase 1/1.5/2 already covers
(nothing here reimplements or removes any of that). One more thing was
found and deliberately left alone; read "What I found but did NOT fix"
before assuming this covers everything in scope.

This builds directly on `docs/VISION_COORDINATE_FIX.md` (the (0,0)/verb-
stripping fix), `docs/CONCURRENCY_AND_VISION_FIXES.md`, and
`docs/BROWSER_THREAD_AFFINITY_FIX.md` — same files, same architecture,
next layer of problems.

## 1. Screenshots that "were taken" but could never be found

**What the report described:** SAM said it took a screenshot; searching
`~/.sam_data`, `~/Projects/SAM`, `/tmp`, and `/private/tmp` never found
it.

**Root cause, confirmed by reading the code:** `ComputerController.
screenshot()`'s default path was bare `tempfile.mktemp(suffix=".png")`
— no `dir=` argument. Python's `tempfile` resolves the OS default temp
directory when you don't give it one, and on macOS that's `$TMPDIR`: a
random, per-boot path under `/var/folders/.../T/`. It is **not**
`/tmp` — `/tmp` on macOS only happens if you pass `dir="/tmp"`
explicitly, which this call never did. (`hands/vision/screen_reader.py`'s
own throwaway screenshots *do* force `/tmp` — that's a completely
separate, transient code path used only to feed the vision model, never
meant to persist for a person to go looking for. The two were never the
same bug.) So the file was always real, saved to a real path — just
never one a person would think to check.

**Fixed:** defaults to `SCREENSHOTS_DIR` (`~/.sam_data/screenshots/`),
consistent with this project's own "everything persists under
`~/.sam_data`" convention (`config/settings.py`'s `SAM_DATA_DIR`),
creating the directory if needed and avoiding same-second filename
collisions. An explicitly-given path is used completely unchanged.
`SCREENSHOTS_DIR` is a small local constant in `hands/control/
controller.py`, not an import from `config/settings.py` — same reason
`SCREENCAPTURE_BIN` is already duplicated there instead of shared:
`hands/` modules stay importable without pulling in `config/settings.py`'s
own import-time side effects (it creates several `~/.sam_data`
subdirectories and reads `settings.yaml` the moment it's imported).

## 2. `open_app` failing on names that were "close enough"

**What the report described:** "Open Spotlight and search for Visual
Studio Code, then launch it" — and generally, no reliable way to launch
a known app by name.

**Root cause, confirmed by reading the code:** two separate gaps
compounded each other.

First, `core/brain.py`'s `SYSTEM_PROMPT` only ever documented `click`
and `type` as control subtypes in its action-payload examples.
`open_app`, `hotkey`, and `screenshot` all existed in the executor
(`agent/react_loop.py`'s `_execute_control`) but were never mentioned to
the model — so it had no way to know `open_app` existed at all, and
would either fall back to visually clicking through Spotlight (Phase 1's
verb-stripping and post-click re-observation help here, but it's still
strictly less reliable than a direct call) or invent a nonexistent
subtype (the "Unknown control action" cases noted in
`VISION_COORDINATE_FIX.md`).

Second, even when `open_app` *was* used, `ComputerController.open_app()`
passed the raw name straight to `tell application "{app_name}" to
activate` with no fallback. "VS Code" is a completely natural thing to
call it, but AppleScript has no application literally named "VS Code" to
resolve — it needs "Visual Studio Code." This is the exact same
name-mismatch `agent/react_loop.py`'s `_same_app()` already works around
— but only *after* activation, to check whether the right app came to
the front. It can't fix a resolution failure before activation ever
succeeds in the first place.

**Fixed, in both places:**
- `core/brain.py`: the prompt now documents all five control subtypes
  (`click`, `type`, `hotkey`, `open_app`, `screenshot`) with an example
  each, and says plainly that `open_app` is the reliable way to launch a
  known app, reserving Spotlight/hotkey+type+click for when the user
  specifically wants the on-screen search UI or `open_app` fails. The
  Phase 1 fix this extends (`"don't repeat the verb"`, the corrected
  click example) is untouched — extended, not replaced.
- `hands/control/controller.py`: `open_app()` now tries the given name,
  then a small known-alias table (`MAC_APP_NAME_ALIASES` — "VS Code",
  "Chrome", the Microsoft Office family; not exclusive to any one app),
  then a fuzzy match (substring or shared-last-word — the same rule
  `_same_app()` uses, reimplemented locally since `hands/` doesn't
  import from `agent/`) against whatever's actually installed in
  `/Applications`, `/System/Applications`, and `~/Applications`. If
  nothing resolves, it raises naming every name it tried, instead of
  reporting only the first, literal failure.

## 3. Actions that silently did nothing

**Found while auditing `hands/control/controller.py`, not reported
directly, but exactly the failure mode Phase 3's scope is about:** every
mouse/keyboard method — `click`, `double_click`, `right_click`,
`move_to`, `scroll`, `drag`, `type_text`, `hotkey`, `press`, `key_down`,
`key_up` — was written as `if self._pyautogui: ...` with no `else`. If
PyAutoGUI wasn't loaded, the call was a complete no-op: no exception, no
log line the caller could see, no return value to check. `agent/
react_loop.py`'s `execute()` only reports what a step's own observation
says happened — with nothing raised here, a click or an entire typed
string could vanish and still read as if it had been attempted. That's
a worse gap than the screenshot/AppleScript false-successes Phase 1
already closed, for the exact reason this phase exists.

**Fixed:** every one of those methods now calls `_require_pyautogui()`
first and raises a clear `RuntimeError` if the backend isn't available.
This flows straight into the existing verified-execution pipeline with
**zero changes needed in `agent/react_loop.py` or `agent/verifier.py`**
— `execute()`'s existing `try/except` already turns any exception into
an honest `"Error executing {action}: ..."` observation, which the
Verifier's existing `"error executing"` signal already catches.

## 4. Clicking without checking where

**Also found while auditing, same file:** `click()`/`move_to()`/etc.
forwarded whatever `(x, y)` they were given straight to PyAutoGUI —
no check that the values were even numeric, let alone on-screen.
PyAutoGUI's own fail-safe only guards the four literal screen *corners*
(a manual-abort mechanism); a value like `(9999, 300)` isn't a corner
and sails straight through.

**Fixed:** `_validate_coords()` rejects non-numeric input and anything
outside the real screen bounds (from `get_screen_size()`), with a
`RuntimeError` naming the bad coordinate and the actual bounds — never
silently clamped to the nearest valid point, which would just substitute
one arbitrary position for another. `drag()` validates both endpoints.
As defense in depth on the *producing* side too: `hands/vision/
screen_reader.py`'s `find_element()` now rejects an out-of-bounds pixel
result the same way it already rejected exact `(0, 0)`, so a bad vision
answer is caught with a specific, logged reason at the source, not two
layers away as a generic controller error.

While in that file: the coordinate convention (vision's normalized
fraction → `pyautogui.size()`-scaled pixel → PyAutoGUI) is now
documented end to end in `find_element()`'s docstring, per this phase's
explicit request to verify the math rather than assume Retina displays
need special handling. They don't — a fraction is resolution-independent
by construction, and scaling by `pyautogui.size()` (not the screenshot's
own raw pixel dimensions) is what keeps it correct regardless of backing
scale factor. Confirmed via `test_coordinate_convention_is_scale_invariant`,
which checks the same `(0.5, 0.5)` maps to the exact center at three
different simulated screen sizes. Nothing about the actual scaling
changed — changing it would have double-applied a correction this
design already gets for free.

## 5. YouTube: reaching the search results but not the video

**What the report described:** SAM can search YouTube but has
difficulty actually clicking/selecting a video and playing it —
generalizes to Spotlight/VS Code and any content-dense results page.

**Root cause, confirmed by reading `hands/browser/playwright_agent.py`:**
`_smart_click()` stripped "click" from the task, split what was left
into individual words, and tried each via Playwright's `text=word`
selector **in left-to-right order, stopping at the first word that
matched anything** — not the first word that matched the *right* thing.
On a content-dense page (a YouTube search-results list full of
recommended/related text, channel names, "Shorts" thumbnails), a
task like "click the video titled 'Some Song'" would very plausibly
match on "some" or "titled" against some unrelated element long before
it got to a word that actually identified the target. This is a direct,
well-evidenced explanation for exactly the reported symptom, and it's
generic — not YouTube-specific — so the same fix helps Spotlight-style
on-screen results too, wherever `_smart_click` is the mechanism in play.

**Fixed:** `_extract_click_targets()` builds an ordered list of
candidates, most specific first — a quoted phrase in the task, then the
task with filler words stripped as one phrase, then (only if nothing
else survived filtering — a fully generic task with no distinguishing
text) individual real words, longest first, deterministically ordered
(see the note in section 7 below on why "deterministic" needed its own
fix). `_smart_click()` tries each via `page.get_by_text(candidate,
exact=False).first` — a case-insensitive substring match scoped to one
element — instead of the old bare `text=` selector strategy.

Verification: the page URL is captured before and after the click, with
a settle wait in between (see next section) so an SPA-style transition
has a chance to land. A changed URL is real, cheap evidence the click
actually navigated somewhere — not just that Playwright's `.click()`
call returned without raising. The resulting messages deliberately reuse
the *exact* failure vocabulary `agent/verifier.py` already recognizes
from the control (vision/PyAutoGUI) click path — `"could not find"`,
`"may not have registered"` — so **one Verifier failure-signal list
covers both click paths with zero changes needed there.**

## 6. The intermittent "No content found" race

**Flagged as unresolved in `docs/ROADMAP_STATUS.md`, root-caused here:**
`_do_execute()` navigated with `wait_until="networkidle"` — which waits
for 500ms of *zero* network activity. Verified via Playwright's own
current guidance (not assumed): pages that keep a persistent connection
open — analytics beacons, websockets, polling — never go idle, so this
risked silently eating the *entire* 30-second timeout on exactly the
kind of page this phase's own acceptance test targets. YouTube is a
textbook example.

**Fixed:** `goto()` now uses `wait_until="domcontentloaded"` (fires
promptly and reliably) plus a new `_settle()` — a short, **bounded**
best-effort wait for network-quiet (`wait_for_load_state("networkidle",
timeout=4000)`, swallowing a timeout rather than propagating it) —
called after navigation and again after a successful `_smart_click()`.
A page that finishes loading quickly still gets the benefit of the
extra settle time; a page that never goes idle simply proceeds after 4
seconds instead of blocking the whole task for 30.

## 7. A non-determinism bug I introduced and caught before shipping

Worth being explicit about, in the same spirit as
`BROWSER_THREAD_AFFINITY_FIX.md`'s "flaw in my first fix attempt, caught
by testing": my first version of the longest-word fallback in
`_extract_click_targets()` sorted a Python `set` of same-length words.
Sets have no defined iteration order, and string hashing is randomized
per-process by default — so the relative order of two equal-length
fallback words (e.g. "first" vs. "video") could differ between separate
runs of the exact same code on the exact same input. Caught this because
a test asserting the exact fallback order passed standalone but failed
when the full suite ran as a sequence of fresh subprocesses (different
hash seeds each time) — not a flaky test, a genuinely non-deterministic
implementation. Fixed by deduping while preserving first-occurrence
order, then using Python's stable sort — the tie-break is now "whichever
word appeared first in the task text," reproducible across runs.
Re-verified across 5 runs with `PYTHONHASHSEED=random` explicitly set.

## What I found but did NOT fix — flagging honestly

- **`core/brain.py`'s bias toward `control` over `browser` for web
  tasks**, and **Reflection's lessons not being fed back into the
  Brain's prompt** — both already flagged as open, scoped-separately
  items in `docs/ROADMAP_STATUS.md`. Real, but not one of this phase's
  nine reforms, and closer to a prompt/behavior redesign than a Hands
  execution-layer bug — left alone rather than folded in unilaterally.
- **`hands/terminal/runner.py` has no pipeline-failure detection** —
  `tests/test_macos_screenshot_and_terminal_exit_offline.py`'s
  `test_terminal_pipeline_failure_is_not_accepted` fails on a clean
  baseline checkout (confirmed before touching anything — see Testing
  below) looking for a `SAM_TERMINAL_FAILED` marker that doesn't exist
  anywhere in `runner.py`. Terminal isn't part of Reforms 1–9 (screen
  capture, vision, click, type, open_app, Spotlight, browser, anti-loop,
  verification) and isn't in this phase's failure reports — left alone.
- **Sovereign/settings attribute mismatches**
  (`sovereign_vision_model`, `sovereign_output_dir`,
  `sovereign_knowledge_collection` missing from `Settings`),
  **`validate_assistant_name` missing from `config.settings`**, and
  **`run_task_with_optional_sovereign_mode` missing from `main.py`** —
  these are the exact "known repository inconsistencies" this phase's
  own brief said not to fix unless they block Hands work. They don't.
  Confirmed and left alone.
- `fastapi`/`pydantic` aren't installed in the sandbox this was built
  in, so the API/iQOO-phase test files can't run here at all (import
  error, not a code bug) — irrelevant to Hands, unrelated to any change
  in this patch, not evaluated either way.

## Testing

Baseline established **before touching any code**: every
`tests/test_*_offline.py` file run once against the untouched checkout.
`tests/test_hands_reliability_offline.py` (Phase 1) passed cleanly —
73/73 — confirming that work is solid as-is and this phase only needed
to build on it, not redo it. The only Hands-adjacent baseline failure
was the terminal-pipeline gap above (4/5 checks in that file already
passed — the 4 screenshot-diagnostic checks in it are untouched by this
phase and still pass). Every other baseline failure was either a missing
package in this sandbox or one of the pre-flagged sovereign/settings
inconsistencies above.

After: the same full suite, run clean (some pre-existing test files —
`test_licensing_offline`, `test_phase2_telegram_offline`,
`test_feature_tier_offline` — write real state to `~/.sam_data`/
`~/.sam_signing_keys` and aren't safely re-runnable without clearing it
first; that's a pre-existing test-isolation gap in files this phase
never touches, not a regression — confirmed by clearing that state and
re-running clean). Result: **every pre-existing test file's pass/fail
status is byte-for-byte identical to the baseline.** Zero regressions.

New: `tests/test_hands_phase3_reliability_offline.py` — 81 checks, all
passing, covering every fix above: the PyAutoGUI-missing guard on all 11
action methods, coordinate bounds validation, the screenshot default
path (deterministic, discoverable, collision-avoiding, explicit-path
still bypasses it entirely), `open_app` name resolution (alias table,
fuzzy substring, fuzzy shared-last-word, unreadable-directory
resilience, "nothing resolves" naming every attempt, "already works"
skipping resolution entirely), vision's out-of-bounds rejection and the
scale-invariance property, the Brain prompt's full vocabulary (plus a
guard against regressing the Phase 1 prompt fix while extending it),
`_extract_click_targets`'s phrase-first/filler-stripped/word-fallback
behavior including the empty-input and fully-generic edge cases, the
full `_smart_click` flow against a mocked page for all three outcomes
(URL changed / unchanged / nothing found) cross-checked against the real
`Verifier`, and `goto`/`_settle`'s new wait behavior.

Run it with:
```
python3 tests/test_hands_phase3_reliability_offline.py
```

## Manual Mac validation checklist

Automated tests can't prove real macOS/browser interaction. Before
calling this done, run all nine on the actual Mac:

| # | Command to SAM | Expected screen state | Expected SAM result | Failure condition |
|---|---|---|---|---|
| 1 | "Open Spotlight." | Spotlight search field visible, focused | Confirms Spotlight is open | Spotlight doesn't appear, or SAM claims success without checking |
| 2 | "Open Spotlight and search for Visual Studio Code, then launch it." | VS Code launches and comes to the foreground | Confirms VS Code is frontmost (or, if it used `open_app` instead of visible Spotlight, confirms that honestly) | VS Code never launches, or SAM reports success while something else is frontmost |
| 3 | "Open Chrome and search YouTube for [a known song]." | YouTube search results for that song are visible | Describes the results found | Wrong site, no results, or a generic/failed page |
| 4 | "Select the requested YouTube video and play it." | The specific requested video's watch page loads and plays | Confirms the click landed on the right video (title match), not an arbitrary result | Wrong video selected, nothing happens, or SAM claims success with the URL unchanged |
| 5 | "Take a screenshot and tell me exactly where it was saved." | — | Reports a path under `~/.sam_data/screenshots/`, and the file exists there | Path reported doesn't exist, or is some other temp location |
| 6 | "Open VS Code." | VS Code launches directly (no Spotlight needed) | Confirms via `open_app`, fast | Falls back to Spotlight-clicking, or fails outright |
| 7 | "Type [a known string] into [a known input]." | The string appears in that field | Observation confirms the field's actual contents, not just "Typed: X" | Field is empty/wrong but SAM reports success |
| 8 | "Click [a known visible UI element]." | That element's expected action happens | Confirms the specific element changed state | A different element gets clicked, or nothing visibly changes but SAM reports success |
| 9 | Give SAM a deliberately impossible/invalid action | Nothing changes on screen | Fails cleanly with a specific diagnostic, does not loop | Repeats the same failed action indefinitely, or claims success |

## Rollback

Every change in this phase is additive/defensive — new guards, a new
default path, a new resolution step, a rewritten single method
(`_smart_click`) — none of it removes or restructures Phase 1/1.5/2
mechanisms. `git diff` against the pre-Phase-3 commit shows the complete,
reviewable set of changes; reverting is a plain `git revert` of this
phase's commit(s), nothing else depends on it yet.
