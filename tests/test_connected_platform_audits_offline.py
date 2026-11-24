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
    ]
    for q in queries:
        decision = router.route(q)
        assert decision.tier == ExecutionTier.DIRECT, f"Failed for query: {q}"
        assert decision.action == "browser", f"Failed for query: {q}"
        assert decision.action_payload["url"] == "https://www.linkedin.com/in/dhanushsurada"
        assert decision.action_payload["use_system_browser"] is True
        assert "dhanushsurada" in decision.suggested_text
        assert "http" in decision.suggested_text


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
        assert decision.action == "browser", f"Failed for query: {q}"
        assert decision.action_payload["url"] == "https://github.com/dhanushsurada"
        assert decision.action_payload["use_system_browser"] is True
        assert "github" in decision.suggested_text.lower()


def test_tiered_router_social_and_ecosystem_audits():
    router = TieredExecutionRouter()
    
    # Twitter / X
    tw_decision = router.route("audit my twitter")
    assert tw_decision.tier == ExecutionTier.DIRECT
    assert tw_decision.action == "browser"
    assert "x.com/dhanushsurada" in tw_decision.action_payload["url"]

    # Instagram
    ig_decision = router.route("audit my instagram")
    assert ig_decision.tier == ExecutionTier.DIRECT
    assert ig_decision.action == "browser"
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
