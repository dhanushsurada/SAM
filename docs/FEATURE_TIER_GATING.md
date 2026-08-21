# Feature-Tier Gating

The piece that makes the license actually restrict something. Before this,
`LicenseManager` could sign, verify, detect tampering/expiry/rollback —
but nothing in SAM checked license status to change behavior. Someone
cloning the repo got the identical experience to a paying customer.

## What changed

**`licensing/tier.py` (new)** — `get_tier(settings)` returns `FREE` or
`PRO`. If `settings.license_enforcement_enabled` is `False` (the current
default), always returns `PRO` — full access, since you're still testing
daily and a licensing bug must never lock you out of your own software.
If enforcement is on, resolves via the existing offline `LicenseManager.check()`.
Fails safe to `FREE` on any error — never crashes, never accidentally
grants access.

**`memory/store.py` / `memory/retrieve.py`** — `get_recent_episodes()` and
`search_semantic()` gained an optional `retention_days` parameter. Free
tier passes `7`; Pro/enforcement-off passes `None` (unlimited, unchanged
default).

**`founder_mode/manager.py`** — `capture_if_relevant()` and `get_context()`
both check tier first. Free tier: no capture, no context, full stop.

**`main.py` / `ecosystem/telegram_bridge.py`** — both wire the same
retention cap into their `retrieve()` calls (mobile parity). `main.py`
additionally gates the spoken "incognito" command behind Pro tier, per
the frozen pricing table.

## Tiers, exactly as frozen

- **Free**: 7-day memory retention, no Founder Mode, no Incognito
- **Pro**: unlimited memory, full Founder Mode, Incognito available

## A regression found and fixed during this work

Two pre-existing tests in `test_task_request_and_stagnation_offline.py`
use `settings = MagicMock()`. `MagicMock` auto-vivifies any attribute
access as a truthy object — so `getattr(settings, "license_enforcement_enabled", False)`
returned a MagicMock, not the literal `False` a real `Settings()` object
has by default. This isn't a production bug (real `Settings()` defaults
cleanly), but it broke test isolation. Fixed by explicitly setting
`settings.license_enforcement_enabled = False` on both mocks.

## Tests

`tests/test_feature_tier_offline.py` — 9/9: enforcement on/off, fail-safe
on garbage input, the 7-day retention cap (verified against a real
15-day-old vs. recent episode), Founder Mode gated when enforced +
unlicensed, Founder Mode fully accessible when enforcement is off.

Full regression: 11 suites, no regressions after the MagicMock fix.

## Rollback

Six files: `licensing/tier.py` (new), `memory/store.py`,
`memory/retrieve.py`, `founder_mode/manager.py`, `main.py`,
`ecosystem/telegram_bridge.py`. Plus one new test file and one test-file
fix.
