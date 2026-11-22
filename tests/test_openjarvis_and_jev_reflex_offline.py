"""
Offline tests for SAM OpenJarvis feature parity and JEV Reflex streaming integration:
- System 1 Streaming Reflex Engine with sub-80ms decision latency
- Speculative context injection & predictive workspace synthesis
- Local Notes Vault with bidirectional auto-logging
- Autonomous Morning Briefing Agent & Proactive Agenda Optimizer
- Multi-Engine Hardware & Energy Profiler (Intelligence Per Watt)
- OpenAI-compatible API endpoints (/v1/models, /v1/chat/completions)
- Tiered routing for briefing and real-life plate queries
"""

import datetime
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.jev_reflex_engine import JevReflexEngine, ReflexDecision
from memory.notes_vault import NotesVaultRetriever
from core.briefing_agent import MorningBriefingAgent, CalendarEvent, EmailItem
from core.engine_manager import EngineManager, HardwareAccelerator
from core.tiered_router import TieredExecutionRouter, ExecutionTier
from api.app import list_v1_models, chat_completions


class MockController:
    def __init__(self):
        self.opened_apps = []

    def open_app(self, app_name: str, background: bool = False):
        self.opened_apps.append((app_name, background))


# ─── 1. JEV Reflex Engine Tests ───────────────────────────────────────────

def test_jev_reflex_engine_fast_app_launch():
    controller = MockController()
    engine = JevReflexEngine(controller=controller)
    engine.reset_stream("utt_1")

    # Partial transcript mid-sentence
    decision = engine.evaluate_partial("can you open Spotify and play")
    assert decision is not None
    assert decision.action == "open_app"
    assert decision.payload["app"] == "Spotify"
    assert decision.executed is True
    assert decision.latency_ms < 50.0  # sub-50ms latency
    assert ("Spotify", True) in controller.opened_apps


def test_jev_reflex_speculative_notes_context_injection():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir)
        daily_note = vault_path / f"{datetime.date.today().isoformat()}.md"
        daily_note.write_text("# Tasks\n- [ ] Ship JEV reflex integration\n- [ ] Fix latency bug\n", encoding="utf-8")

        vault = NotesVaultRetriever(notes_dir=vault_path)
        engine = JevReflexEngine(notes_vault=vault)
        engine.reset_stream("utt_2")

        # User speaking mid-sentence asking about their plate
        decision = engine.evaluate_partial("tell me what's on my plate from my real life")
        assert decision is not None
        assert decision.action == "search_notes"
        assert decision.executed is True
        assert "Ship JEV reflex integration" in decision.context_injected
        assert engine.get_speculative_context() is not None
        assert "Ship JEV reflex integration" in engine.get_speculative_context()


def test_jev_reflex_stream_idempotency():
    controller = MockController()
    engine = JevReflexEngine(controller=controller)
    engine.reset_stream("utt_3")

    # First partial trigger
    d1 = engine.evaluate_partial("open Chrome")
    assert d1 is not None
    assert len(controller.opened_apps) == 1

    # Second partial in the same sentence should NOT re-trigger app launch
    d2 = engine.evaluate_partial("open Chrome and search for machine learning papers")
    assert d2 is None
    assert len(controller.opened_apps) == 1

    # New stream should allow next trigger
    engine.reset_stream("utt_4")
    d3 = engine.evaluate_partial("open Safari")
    assert d3 is not None
    assert len(controller.opened_apps) == 2


# ─── 2. Local Notes Vault & Bidirectional Auto-Log Tests ───────────────────

def test_notes_vault_retrieval_and_bidirectional_log():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = NotesVaultRetriever(notes_dir=Path(tmpdir))

        # Test initial empty plate
        plate = vault.get_active_plate()
        assert "clear" in plate.lower()

        # Write a sample note
        today_file = vault.get_today_note_path()
        today_file.write_text("# Today\n- [ ] Design System 1 Reflexes\nPriority: High\nProject: SAM Upgrade\n", encoding="utf-8")

        plate_updated = vault.get_active_plate()
        assert "Design System 1 Reflexes" in plate_updated
        assert "SAM Upgrade" in plate_updated

        # Test bidirectional note auto-log
        success = vault.append_daily_log("Opened Spotify and pre-warmed notes", category="Reflex")
        assert success is True

        content = today_file.read_text(encoding="utf-8")
        assert "## SAM Activity Log" in content
        assert "Opened Spotify and pre-warmed notes" in content


# ─── 3. Morning Briefing Agent & Agenda Optimizer Tests ───────────────────

def test_morning_briefing_agent_and_optimizer():
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = NotesVaultRetriever(notes_dir=Path(tmpdir))
        today_file = vault.get_today_note_path()
        today_file.write_text("# Daily\n- [ ] Prepare investor briefing\n", encoding="utf-8")

        agent = MorningBriefingAgent(notes_vault=vault)

        # Mock calendar events and emails
        mock_events = [
            CalendarEvent(title="Sprint Standup", start_time="9:30 AM", is_virtual=True),
            CalendarEvent(title="Architecture Review", start_time="2:00 PM", is_virtual=True),
        ]
        mock_emails = [
            EmailItem(subject="URGENT: Server latency report", sender="DevOps Team", is_urgent=True)
        ]

        with patch.object(agent, "get_calendar_events", return_value=mock_events), \
             patch.object(agent, "get_unread_emails", return_value=mock_emails):
            briefing = agent.generate_briefing()

            assert "Sprint Standup" in briefing.spoken_summary
            assert "URGENT" in briefing.executive_markdown
            assert "Prepare investor briefing" in briefing.notes_tasks
            assert len(briefing.events) == 2
            assert briefing.optimization.next_meeting_prep is not None
            assert "Sprint Standup" in briefing.optimization.next_meeting_prep


# ─── 4. Multi-Engine & Energy Profiler Tests ──────────────────────────────

def test_engine_manager_hardware_and_energy():
    mgr = EngineManager()
    hw = mgr.hardware
    assert hw.accelerator in (
        HardwareAccelerator.APPLE_SILICON_METAL,
        HardwareAccelerator.NVIDIA_CUDA,
        HardwareAccelerator.CPU_ONLY,
    )
    assert hw.total_memory_mb > 0

    # Test Intelligence Per Watt energy calculation
    energy = mgr.profile_energy_and_throughput(tokens_generated=150, duration_seconds=3.0)
    assert energy.tokens_per_second == 50.0
    assert energy.estimated_joules_per_token > 0.0
    assert energy.total_energy_joules > 0.0


# ─── 5. OpenAI-Compatible API Endpoints Tests ──────────────────────────────

def test_openai_compatible_endpoints():
    # Test /v1/models
    models_res = list_v1_models()
    assert models_res["object"] == "list"
    model_ids = [m["id"] for m in models_res["data"]]
    assert "sam-brain" in model_ids
    assert "sam-fast-reflex" in model_ids

    # Test /v1/chat/completions non-streaming
    req = {
        "model": "sam-brain",
        "messages": [
            {"role": "user", "content": "hi"}
        ],
        "stream": False
    }
    resp = chat_completions(req)
    assert resp["object"] == "chat.completion"
    assert len(resp["choices"]) == 1
    assert "SAM" in resp["choices"][0]["message"]["content"]
    assert resp["usage"]["total_tokens"] > 0


# ─── 6. Tiered Router Briefing & Plate Checks ─────────────────────────────

def test_tiered_router_briefing_and_notes():
    router = TieredExecutionRouter()

    # Morning briefing direct execution
    d1 = router.route("give me my morning briefing")
    assert d1.tier == ExecutionTier.DIRECT
    assert d1.action == "morning_briefing"
    assert "briefing" in d1.suggested_text.lower() or "good morning" in d1.suggested_text.lower()

    # Real-life plate query direct execution
    d2 = router.route("what's on my plate from my real life")
    assert d2.tier == ExecutionTier.DIRECT
    assert d2.action == "check_plate"
    assert "plate" in d2.suggested_text.lower() or "notes" in d2.suggested_text.lower()
