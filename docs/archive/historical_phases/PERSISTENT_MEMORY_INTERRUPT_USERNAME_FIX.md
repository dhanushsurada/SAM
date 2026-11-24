# Persistent Memory Fix + Interrupt/Stop + GitHub Username Update

Status: ready to commit. Built on your uploaded zip (confirmed identical to
the last delivery, no manual edits found), not a stale recovered copy.

## Fix 1 — Persistent memory connections (real, confirmed bug)

**Root cause, precisely traced:** `Session.save()` was constructing a
brand new `MemoryStore()` — fresh SQLite connection, fresh ChromaDB
init — on *every single turn*, completely independent of
`MemoryRetriever`'s already-correct caching. This exactly matches the
`[SAM.MemoryStore] INFO: SQLite at .../episodic.db` / `ChromaDB at
.../chroma` lines appearing after every response in every Mac log across
this entire project.

**Fixed:** `MemoryRetriever` gained a public `get_store()` method exposing
its already-cached store. `Session.save()` now accepts an optional
`memory_store` parameter — pass it the cached store and it reuses the
exact connection `retrieve()` already opened this turn, instead of
opening a second, parallel one. Both `main.py` and the Telegram bridge
now pass it in. Omit it and the old behavior is unchanged — fully
backward compatible.

**Verified:** simulated 5 full turns (retrieve + save each) — confirmed
exactly 1 `MemoryStore` initialization total, not 5, not 10.

## Fix 2 — Interrupt/Stop (the actual "stop it" bug, fixed properly)

**Root cause, precisely traced:** `_process()` acquired `self._process_lock`
*before* calling `_handle_command()`. So when a task was running and you
typed "stop it," that message tried to acquire the same lock the running
task held — and just queued behind it, waiting for the task to finish on
its own before "stop" ever got a chance to do anything. That's exactly
what your test log showed.

**Fixed:** stop/cancel phrases ("stop", "stop it", "cancel", "abort",
"never mind") are now intercepted in `_process()` **before** the lock is
ever touched. Setting a `threading.Event()` is instant regardless of
whether the lock is held. `ReactLoop.run_task()` and `run_planned_task()`
now check that event between every single step and abort immediately —
"Stopped." — instead of continuing. The event clears automatically right
before a new task starts, so a stale cancel from a previous interrupted
task can't kill the next one before it begins.

**Verified:**
- A cancel set *before* a task starts aborts immediately — the Brain is
  never even called once.
- A cancel set *mid-task* (simulating a real interrupt arriving between
  steps) stops the loop at exactly that step, not after running to
  `MAX_STEPS`.

## Fix 3 — GitHub username update

Swept the entire codebase for `suradadhanush` — found and fixed one
occurrence, in `README.md`'s contact line. Confirmed zero remaining
occurrences anywhere (`.py`, `.md`, `.txt`, `.yaml`, `.json`, and a
broader `github.com/surada*` pattern check). This only covers the `SAM`
repo itself — your other repos (`anoncampus`, `nsrit-esports-arena`, your
personal `suradadhanush` repo) would need the same sweep separately if
they mention the old username anywhere; upload them if you want that
done too. GitHub itself auto-redirects the old profile URL, so links
pointing at `github.com/suradadhanush` won't break, but updating them is
still worth doing for accuracy.

## Tests run before packaging

- New: `tests/test_persistent_memory_offline.py` — 3/3 (single connection
  reused across 5 turns, backward compatibility, incognito mode
  unaffected).
- Interrupt/cancel logic tested directly in this conversation (pre-set
  and mid-task cancellation, both confirmed) — not yet a committed test
  file; flag if you want that formalized too.
- Full regression across all 10 existing suites — no regressions.

## Rollback

Five files touched: `memory/retrieve.py` (+1 public method),
`core/session.py` (`save()` gains 1 optional parameter, old behavior
preserved), `main.py` (+cancel event, +stop-phrase interception, +clear
before new task), `agent/react_loop.py` (`run_task`/`run_planned_task`
gain 1 optional parameter each, checked between steps),
`ecosystem/telegram_bridge.py` (1 line, passes the cached store into
save()). `README.md` (1 line, username). `git diff` against your current
repo state shows the full blast radius.

## Still owed from the last few turns

The corrected phase-map reconciling both external planning documents
against actual ground truth (both got real things wrong — one claims a
GUI already exists, which it doesn't at all; both reuse "Phase 1.5" for a
different feature set than what's already shipped under that name).
Coming next, not forgotten.
