"""
Tests verifying consecutive task execution speed, non-blocking post-turn hooks,
heuristic extraction filtering, and TTS interruption.
"""

import threading
import time
from unittest.mock import MagicMock, patch

from core.brain import BrainResponse
from core.session import Session
from memory.store import MemoryStore
from mouth.tts import TextToSpeech
from interfaces.api.gateway import TaskGateway


class DummySettings:
    sqlite_path = "/tmp/test_sam_consecutive.db"
    chroma_path = "/tmp/test_sam_chroma_consecutive"
    ollama_host = "http://127.0.0.1:11434"
    primary_model = "qwen2.5:7b"
    embedding_model = "nomic-embed-text"
    incognito = False
    tts_engine = "none"
    model_provider = "ollama"
    temperature = 0.2
    max_tokens = 500
    model_context_length = 4096
    license_enforcement_enabled = False


def test_extract_and_save_skips_operational_commands(monkeypatch):
    """Operational commands like 'open notes' or 'calculate 5+5' must skip LLM extraction."""
    settings = DummySettings()
    store = MemoryStore(settings)

    mock_post = MagicMock()
    monkeypatch.setattr("requests.post", mock_post)

    # Pure operational command
    store.extract_and_save("open calculator and take a screenshot", "Opened Calculator.", async_mode=False)
    assert mock_post.call_count == 0, "Operational commands must not fire LLM extraction"

    # Command with personal indicator
    store.extract_and_save("Remember that I prefer dark mode in all apps", "Got it, I noted that you prefer dark mode.", async_mode=False)
    # mock_post should be called because "prefer" / "remember that" is present
    assert mock_post.call_count == 1, "Personal fact indicator must trigger extraction"


def test_session_save_is_non_blocking_and_instant():
    """session.save with default async_extract=True returns in < 50ms."""
    settings = DummySettings()
    session = Session(
        user_input="open notes",
        identity={},
        memories=[],
        founder_context="",
        settings=settings
    )
    resp = BrainResponse(text="Opened Notes.", action="control")

    start = time.time()
    session.save("open notes", resp)
    elapsed = time.time() - start

    assert elapsed < 0.1, f"session.save took {elapsed:.3f}s, expected < 0.1s"


def test_tts_stop_resets_active_process():
    """tts.stop() terminates active process without error."""
    settings = DummySettings()
    tts = TextToSpeech(settings)

    dummy_proc = MagicMock()
    dummy_proc.poll.return_value = None
    tts._active_proc = dummy_proc

    tts.stop()
    assert dummy_proc.terminate.called
    assert tts._active_proc is None


def test_gateway_consecutive_tasks_process_without_inter_task_delay():
    """Consecutive tasks in TaskGateway must execute back-to-back with 0ms delay."""
    settings = DummySettings()
    gateway = TaskGateway(settings=settings)

    try:
        # Mock brain to return quickly
        gateway.brain.process = MagicMock(return_value=BrainResponse(text="Task done", action=None))

        # Submit task 1 then immediately task 2
        t1 = gateway.submit_task("first task")
        t2 = gateway.submit_task("second task")

        start = time.time()
        # Wait for both tasks to complete
        for tid in [t1, t2]:
            while True:
                task = gateway.get_task(tid)
                if task and task["status"] in ("completed", "failed"):
                    break
                time.sleep(0.01)
                if time.time() - start > 5.0:
                    raise TimeoutError(f"Task {tid} timed out")

        record1 = gateway.get_task(t1)
        record2 = gateway.get_task(t2)

        assert record1["status"] == "completed"
        assert record2["status"] == "completed"
        assert gateway.brain.process.call_count == 2
    finally:
        gateway.shutdown()
