"""
LICENSING — Feature Tier (the piece that makes the license actually matter)

Everything built in Phase 3 before this file could sign, verify, detect
tampering, and detect expiry — but nothing in SAM actually CHECKED
license status to change behavior. Someone cloning the repo got the
identical experience to a paying customer. This module is the fix: a
single, cheap, cached tier lookup that the rest of the app gates real
features on.

Per the frozen monetization table:
  Free  — 7-day memory retention, no Founder Mode, no Incognito
  Pro   — unlimited memory, full Founder Mode, Incognito available

No network check, ever — reads the same offline LicenseManager.check()
already built and tested. Tier resolution is itself entirely offline.
"""

import logging

logger = logging.getLogger("SAM.Licensing.Tier")

FREE = "free"
PRO = "pro"

FREE_TIER_MEMORY_RETENTION_DAYS = 7


def get_tier(settings=None, license_manager=None) -> str:
    """
    Returns FREE or PRO. Fails safe toward FREE on any error — an
    exception here must never accidentally grant Pro access, and must
    never crash the caller (tier checks happen on hot paths like every
    memory retrieval and every Founder Mode call).
    """
    try:
        if settings is not None and not getattr(settings, "license_enforcement_enabled", False):
            # Enforcement is off (the current default — you're still
            # testing daily, a licensing bug must never lock you out of
            # your own software). Full access regardless of license status.
            return PRO

        if license_manager is None:
            from licensing.license_manager import LicenseManager
            license_manager = LicenseManager()

        from licensing.license_manager import LicenseStatus
        status, _, _ = license_manager.check()
        return PRO if status == LicenseStatus.VALID else FREE

    except Exception as e:
        logger.debug(f"Tier resolution failed, defaulting to FREE (fail-safe): {e}")
        return FREE
