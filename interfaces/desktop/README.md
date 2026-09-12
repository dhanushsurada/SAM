# SAM Desktop (Phase 5)

The full SAM product UI — not `frontend/` (that's VEDA, a different product
for a different hackathon) and not `interfaces/web/` (SAM's existing narrow
iQOO phone client, left untouched).

See `../../docs/frontend/PHASE5_PLAN.md` for the full plan: capability map,
architecture decisions, directory structure, page inventory, design system,
the real-vs-demo backend boundary, and implementation order.

## Setup

```bash
cd interfaces/desktop
npm install
npm run dev
```

Needs network access for `npm install` — this codebase was authored in a
sandbox without it, so it's been verified with local `tsc` against a type
shim rather than a real build. See the next section before you run it.

## About `src/types/react-shim.d.ts`

This file exists only because the code was written somewhere without
network access to install `@types/react`. It's a minimal, deliberately
incomplete stand-in that let local `tsc` catch real mistakes (wrong prop
names, missing required props) during authoring. Once you run `npm install`
here, you'll have the real type packages — delete `react-shim.d.ts` at that
point; keeping both around will cause duplicate-declaration errors.

Expect a handful of normal first-run issues after that — a hand-authored
scaffold that's never seen a real `npm install` typically needs a small
amount of settling, same as any fresh project would.

## What's real vs. demo right now

Only the iQOO gateway (`interfaces/api/server.py`) is a live backend today.
Everything else in this app (Chat, Memory, Founder Mode, Skills, Models,
Diagnostics, Licensing) is UI built ahead of a backend that doesn't exist
yet — each will be clearly marked DEMO in the interface itself, never
presented as live. Full breakdown, with the exact endpoints each would need,
is in `PHASE5_PLAN.md` §F.

## Status

All 10 steps of the plan's implementation order (`PHASE5_PLAN.md` §H) are
done — 63 files.

- Design tokens (light + dark, two values corrected by computed WCAG
  contrast — see §H step 10), globals, shared components (`Button`,
  `StatusPill`, `ModeBadge`, `EmptyState`, `PageHeader`, `Switch`)
- App shell — sidebar, top bar, routing, persisted theme toggle, a real
  mobile drawer, skip-to-content link, Escape-to-close
- Typed API client (`src/api/`) mirroring `interfaces/api/schemas.py`
  field-for-field, plus the `iqoo` service layer and shared task-session
  state (`src/stores/taskSession.tsx`)
- **`/` and `/iqoo` are real** — same live gateway
- **`/chat` is an honestly-labeled demo** — every reply says so in its own
  text, not just a badge
- **`/memory`, `/founder-mode`, `/skills`, `/models`, `/diagnostics`,
  `/licensing`, `/settings`** — demo, each grounded in a real backend
  shape
- **`/onboarding`** — standalone wizard; system check is real, everything
  a browser genuinely can't verify is informational rather than faked
- `/tasks` is the only route left on the shared `PLANNED` stub

Two real bugs found and fixed while building the iQOO integration, and
two real WCAG contrast failures found and fixed in the final pass — all
four documented with the actual numbers in `PHASE5_PLAN.md` §H, not just
asserted. That file also says plainly what the accessibility pass did
*not* cover (no real browser/screen-reader testing was possible here,
border contrast wasn't computed, the mobile drawer has no full focus trap)
— worth reading before treating this as a finished audit rather than a
solid first pass.

**Not done, and not pretended to be:** every backend endpoint this UI
would need to stop being a demo is listed with request/response shape and
priority in `PHASE5_PLAN.md` §F. Nothing in this app claims a capability
the repository doesn't actually have.
