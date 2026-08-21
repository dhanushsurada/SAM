"""
Offline test suite for feature-tier gating — the actual enforcement
mechanism that was missing after Phase 3. Before this, license
verification existed but nothing checked it to restrict behavior.

Tests both states:
- license_enforcement_enabled=False (current default — full access)
- license_enforcement_enabled=True with no license installed (the real
  free-tier experience: 7-day memory, no Founder Mode, no Incognito)

Usage:
    HOME=/tmp/sam_smoke_tier python3 tests/test_feature_tier_offline.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import Settings  # noqa: E402
from licensing.tier import get_tier, FREE, PRO, FREE_TIER_MEMORY_RETENTION_DAYS  # noqa: E402
from memory.store import MemoryStore  # noqa: E402
from founder_mode.manager import FounderModeManager  # noqa: E402

results = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    results.append(condition)
    print(f"[{status}] {label}")


class FakeResponse:
    text = "ok"


def test_enforcement_off_is_full_access():
    settings = Settings()
    settings.license_enforcement_enabled = False
    check("Enforcement off -> PRO regardless of license status", get_tier(settings) == PRO)


def test_enforcement_on_no_license_is_free():
    settings = Settings()
    settings.license_enforcement_enabled = True
    check("Enforcement on, no license installed -> FREE", get_tier(settings) == FREE)


def test_tier_resolution_never_raises():
    try:
        result = get_tier(settings=None, license_manager="not a real manager")
        check("Tier resolution fails safe (FREE) on garbage input, doesn't crash", result == FREE)
    except Exception as e:
        check(f"Tier resolution fails safe on garbage input — FAILED, raised: {e}", False)


def test_memory_retention_gate():
    settings = Settings()
    store = MemoryStore(settings)

    old_ts = (datetime.now() - timedelta(days=15)).isoformat()
    recent_ts = datetime.now().isoformat()
    with sqlite3.connect(store._db_path) as conn:
        conn.execute("INSERT INTO episodes (timestamp, user_input, response, action) VALUES (?,?,?,?)",
                     (old_ts, "old", "old resp", None))
        conn.execute("INSERT INTO episodes (timestamp, user_input, response, action) VALUES (?,?,?,?)",
                     (recent_ts, "recent", "recent resp", None))
        conn.commit()

    unlimited = store.get_recent_episodes(limit=10, retention_days=None)
    capped = store.get_recent_episodes(limit=10, retention_days=FREE_TIER_MEMORY_RETENTION_DAYS)

    check("Unlimited (Pro) retrieval sees both old and recent episodes", len(unlimited) == 2)
    check("Free-tier 7-day cap excludes the 15-day-old episode", len(capped) == 1)
    check("Free-tier cap keeps the recent one", capped[0]["user"] == "recent" if capped else False)


def test_founder_mode_gated_when_enforced_and_unlicensed():
    settings = Settings()
    settings.license_enforcement_enabled = True
    mgr = FounderModeManager(settings=settings)

    mgr.capture_decision("Use FastAPI", "because reasons", "general")
    ctx = mgr.get_context()
    check("Founder Mode context is empty on free tier (enforcement on, no license)", ctx == "")

    mgr.capture_if_relevant("I decided to use Django because of the admin panel", FakeResponse())
    after = len(mgr._get_recent_decisions(50))
    check("capture_if_relevant is a no-op on free tier", after == 1)


def test_founder_mode_full_access_when_enforcement_off():
    settings = Settings()
    settings.license_enforcement_enabled = False
    mgr = FounderModeManager(settings=settings)

    mgr.capture_decision("Use FastAPI", "because reasons", "general")
    ctx = mgr.get_context()
    check("Founder Mode context is populated when enforcement is off (default)", "FastAPI" in ctx)


def main():
    test_enforcement_off_is_full_access()
    test_enforcement_on_no_license_is_free()
    test_tier_resolution_never_raises()
    test_memory_retention_gate()
    test_founder_mode_gated_when_enforced_and_unlicensed()
    test_founder_mode_full_access_when_enforcement_off()

    print(f"\n{sum(results)}/{len(results)} checks passed.")
    if not all(results):
        sys.exit(1)
    print("Feature-tier gating verified.")


if __name__ == "__main__":
    main()
