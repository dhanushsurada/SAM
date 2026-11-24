"""
Offline tests for Connected Platform and Profile Audits:
- Zero-URL prompting for connected platforms (LinkedIn, GitHub, Twitter/X, Instagram)
- Identity connected_platforms structure, canonical URL resolution, and persistence
- Tier 1 Reflex Router execution (<1ms decision without LLM latency)
- Brain system context and conversational audit reflexes
- API /api/profile/ecosystem and /api/profile/ecosystem/sync endpoints
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.identity import Identity
from core.tiered_router import TieredExecutionRouter, ExecutionTier
from core.brain import Brain
from core.session import Session
from config.settings import Settings


def test_identity_connected_platforms_defaults_and_helpers():
    identity = Identity()
    data = identity.load()
    assert "connected_platforms" in data

    gh = identity.get_platform("github")
    assert gh is not None
    assert gh["handle"] == "dhanushsurada"
    assert identity.get_platform_url("github") == "https://github.com/dhanushsurada"

    li = identity.get_platform("linkedin")
    assert li is not None
    assert li["handle"] == "dhanushsurada"
    assert identity.get_platform_url("linkedin") == "https://www.linkedin.com/in/dhanushsurada"

    tw = identity.get_platform("twitter")
    assert tw is not None
    assert identity.get_platform_url("twitter") == "https://x.com/dhanushsurada"

    ig = identity.get_platform("instagram")
    assert ig is not None
    assert identity.get_platform_url("instagram") == "https://www.instagram.com/dhanushsurada"


def test_identity_set_platform_canonical_resolution():
    identity = Identity()
    # Test adding/updating a platform with handle only
    identity.set_platform("github", {"handle": "octocat", "name": "GitHub"})
    assert identity.get_platform_url("github") == "https://github.com/octocat"

    identity.set_platform("linkedin", {"handle": "satyanadella", "name": "LinkedIn"})
    assert identity.get_platform_url("linkedin") == "https://www.linkedin.com/in/satyanadella"

    # Reset back to default
    identity.set_platform("github", {"handle": "dhanushsurada", "name": "GitHub"})
    identity.set_platform("linkedin", {"handle": "dhanushsurada", "name": "LinkedIn"})
    assert identity.get_platform_url("github") == "https://github.com/dhanushsurada"
    assert identity.get_platform_url("linkedin") == "https://www.linkedin.com/in/dhanushsurada"


def test_tiered_router_linkedin_audit_reflex():
    router = TieredExecutionRouter()
    
    queries = [
        "audit my linkedin",
        "audit linkedin",
        "review my linkedin profile",
        "inspect my linkedin",
        "can you audit my linkedin profile",
        "i need a complete detailed audit lie whats the growth ratio how the page is perfoming and what all needs to be done to increase the growth of the page",
        "perform an indeatil audit regarding my linkedin page an suggest me the nest week plan of maintaining the linkedin of mineg",
    ]
    for q in queries:
        decision = router.route(q)
        assert decision.tier == ExecutionTier.DIRECT, f"Failed for query: {q}"
        assert decision.action in ("audit", "browser"), f"Failed for query: {q}"
        assert "url" in decision.action_payload, f"Failed for query: {q}"
        assert "dhanushsurada" in decision.action_payload["url"]
        assert "linkedin" in decision.action_payload["url"]


def test_tiered_router_github_audit_reflex():
    router = TieredExecutionRouter()
    
    queries = [
        "audit my github",
        "audit github",
        "review my github repositories",
        "inspect my github",
    ]
    for q in queries:
        decision = router.route(q)
        assert decision.tier == ExecutionTier.DIRECT, f"Failed for query: {q}"
        assert decision.action in ("audit", "browser"), f"Failed for query: {q}"
        assert "github.com/dhanushsurada" in decision.action_payload["url"]


def test_platform_audit_engine_growth_and_7day_plan():
    from core.audit_engine import PlatformAuditEngine
    engine = PlatformAuditEngine()
    result = engine.audit("linkedin")
    assert result["platform"] == "linkedin"
    assert "https://www.linkedin.com/in/dhanushsurada" in result["url"]
    report = result["report"]
    assert "Growth Ratio" in report
    assert "7-Day Plan" in report
    assert "Next-Week Execution" in report
    assert result["score"] >= 80


def test_mac_audio_guard_offline():
    from mouth.mac_audio import MacAudioGuard
    settings = MacAudioGuard.get_volume_settings()
    assert "volume" in settings
    assert "muted" in settings
    # Test ensure and restore
    ensure_res = MacAudioGuard.ensure_audible(target_volume=70)
    assert ensure_res["ok"] is True
    restore_res = MacAudioGuard.restore_audible()
    assert restore_res["ok"] is True


def test_react_loop_morning_briefing_execution():
    from agent.react_loop import ReactLoop
    from config.settings import Settings
    loop = ReactLoop(Settings())
    res = loop.execute("morning_briefing", {})
    assert res is not None
    assert "briefing" in res.lower() or len(res) > 20
    assert "unknown action" not in res.lower()


def test_tiered_router_social_and_ecosystem_audits():
    router = TieredExecutionRouter()
    
    # Twitter / X
    tw_decision = router.route("audit my twitter")
    assert tw_decision.tier == ExecutionTier.DIRECT
    assert tw_decision.action in ("audit", "browser")
    assert "x.com/dhanushsurada" in tw_decision.action_payload["url"]

    # Instagram
    ig_decision = router.route("audit my instagram")
    assert ig_decision.tier == ExecutionTier.DIRECT
    assert ig_decision.action in ("audit", "browser")
    assert "instagram.com/dhanushsurada" in ig_decision.action_payload["url"]

    # Full ecosystem
    eco_decision = router.route("audit my connected platforms")
    assert eco_decision.tier == ExecutionTier.DIRECT
    assert eco_decision.action == "browser"
    assert "ecosystem" in eco_decision.reason.lower()


def test_brain_build_messages_includes_platform_audit_rules():
    settings = Settings()
    brain = Brain(settings)
    identity = Identity().load()
    
    session = Session(
        user_input="How is my profile performing?",
        identity=identity,
        memories=[],
        founder_context="Values efficiency and direct execution.",
        settings=settings,
    )
    
    messages = brain._build_messages(session)
    system_messages = [m["content"] for m in messages if m["role"] == "system"]
    combined_system = "\n".join(system_messages)
    
    # Verify that connected platforms and explicit zero-URL audit rules are injected
    assert "Verified Connected Platforms & Profiles:" in combined_system
    assert "https://www.linkedin.com/in/dhanushsurada" in combined_system
    assert "https://github.com/dhanushsurada" in combined_system
    assert "NEVER prompt or ask the user for their profile URL" in combined_system


def test_brain_chat_reflex_for_audits():
    settings = Settings()
    brain = Brain(settings)
    
    reply_li = brain.chat("audit my linkedin")
    assert "linkedin" in reply_li.lower()
    assert "https://www.linkedin.com/in/dhanushsurada" in reply_li
    assert "url" not in reply_li.lower() or "https://" in reply_li  # Never asking for URL

    reply_gh = brain.chat("audit my github")
    assert "github" in reply_gh.lower()
    assert "https://github.com/dhanushsurada" in reply_gh
