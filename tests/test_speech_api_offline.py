"""
Voice Phase A — the server side of touch-to-talk:

  * POST /api/speech (text -> WAV with SAM's own voice, loopback only)
  * the structured "heard" transcript event on voice tasks
  * first-use hardening of the audio adapter (a failed model download is
    retried and explained; faster-whisper installed later is picked up)
  * a successful dependency repair makes a newly installed speech engine
    usable without restarting the API

Offline: no TTS engine, Whisper model, microphone, speaker or Ollama is
touched. Kokoro is a fake pipeline, the gateway's Brain/ReAct/adapters are
mocks (same construction pattern as tests/test_iqoo_phase2_offline.py), and
the task database lives in a temp directory. These prove the HTTP contract
and the plumbing; they do NOT prove that real Kokoro/Piper/Whisper work on a
real machine.

Plain pytest functions with real asserts on purpose: CI runs `pytest tests`,
and the script-style suites in this directory use a check() helper that
cannot fail under pytest.
"""

import base64
import io
import json
import sys
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

import interfaces.api.server as server  # noqa: E402
from interfaces.api.events import EventBus  # noqa: E402
from mouth.tts import TextToSpeech, _EngineMissing  # noqa: E402
from multimodal.audio.adapter import AudioAdapter  # noqa: E402
from multimodal.errors import PerceptionError  # noqa: E402

FAKE_WAV = base64.b64encode(b"RIFF" + b"fake wav bytes for offline testing" * 4).decode()
LOOPBACK = ("127.0.0.1", 12345)
LAN_PEER = ("192.168.1.50", 12345)


def make_settings(engine="kokoro"):
    return SimpleNamespace(tts_engine=engine, kokoro_voice="af_bella",
                           speech_rate=1.0, piper_model="en_US-lessac-medium",
                           whisper_model="base.en", api_auth_token="")


class FakeKokoro:
    """Stands in for kokoro.KPipeline."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        return iter([("g", "p", np.array([0.0, 0.5, -0.5], dtype=np.float32))])


@pytest.fixture
def speech(monkeypatch):
    """A TestClient for the real FastAPI app whose speech engine is a fake
    Kokoro and whose settings object is shared the way the real gateway
    shares it."""
    settings = make_settings()
    monkeypatch.setattr(server, "_gateway", SimpleNamespace(settings=settings))
    tts = TextToSpeech(settings)
    tts._kokoro_pipeline = FakeKokoro()
    tts._kokoro_loaded = True
    monkeypatch.setattr(server, "_tts", tts)
    return SimpleNamespace(
        client=TestClient(server.app, client=LOOPBACK),
        remote=TestClient(server.app, client=LAN_PEER),
        settings=settings, tts=tts, kokoro=tts._kokoro_pipeline,
    )


# ─── POST /api/speech ────────────────────────────────────────────────────

def test_speech_returns_a_playable_wav_and_is_never_cached(speech):
    response = speech.client.post("/api/speech", json={"text": "Hello there"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.headers["cache-control"] == "no-store"
    with wave.open(io.BytesIO(response.content)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 24000)
        assert wav.getnframes() == 3
    assert speech.kokoro.calls[0][0] == "Hello there"


def test_speech_strips_markdown_before_speaking(speech):
    speech.client.post("/api/speech", json={"text": "**Done.** I ran `ls`."})
    assert speech.kokoro.calls[0][0] == "Done. I ran ls."


def test_speech_accepts_exactly_the_length_limit(speech):
    assert speech.client.post("/api/speech", json={"text": "a" * 2000}).status_code == 200


@pytest.mark.parametrize("body", [{}, {"text": ""}, {"text": "a" * 2001}, {"text": 5}])
def test_speech_rejects_invalid_bodies_with_422_and_renders_nothing(speech, body):
    assert speech.client.post("/api/speech", json=body).status_code == 422
    assert speech.kokoro.calls == []


def test_speech_rejects_text_with_nothing_to_say_with_a_readable_reason(speech):
    response = speech.client.post("/api/speech", json={"text": "   \n  "})
    assert response.status_code == 422
    assert response.json()["detail"] == "Nothing to speak"  # a string: the desktop client shows it
    assert speech.kokoro.calls == []


def test_speech_is_loopback_only(speech):
    response = speech.remote.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 403
    assert speech.kokoro.calls == []  # refused before any synthesis


def test_speech_off_returns_409_so_the_client_stays_silent(speech):
    speech.settings.tts_engine = "none"
    response = speech.client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 409
    assert "turned off" in response.json()["detail"]
    assert speech.kokoro.calls == []


def test_system_voice_returns_501_so_the_client_can_use_its_own_voice(speech):
    speech.settings.tts_engine = "system"
    response = speech.client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 501
    assert "system voice" in response.json()["detail"]


def test_no_installed_engine_returns_501_naming_each_failure(speech):
    def _synth_kokoro(text):
        raise _EngineMissing("Kokoro not available")

    def _synth_piper(text):
        raise _EngineMissing("Piper not found in PATH")

    speech.tts._synth_kokoro, speech.tts._synth_piper = _synth_kokoro, _synth_piper
    response = speech.client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert "kokoro: not installed" in detail and "piper: not installed" in detail


def test_an_engine_crash_returns_501_without_paths_or_internals(speech):
    """The error text of a crashed engine can hold file paths and command
    lines; the response body carries a fixed reason only."""
    def _synth_kokoro(text):
        raise RuntimeError("model file /home/someone/.cache/kokoro.pt is corrupt")

    def _synth_piper(text):
        raise OSError("[Errno 2] No such file or directory: '/opt/piper-secret/en_US.onnx'")

    speech.tts._synth_kokoro, speech.tts._synth_piper = _synth_kokoro, _synth_piper
    response = speech.client.post("/api/speech", json={"text": "Hello"})
    assert response.status_code == 501
    detail = response.json()["detail"]
    assert "kokoro: failed" in detail and "piper: failed" in detail
    for leaked in ("/home/someone", "/opt/piper-secret", ".onnx", "Errno", "corrupt"):
        assert leaked not in detail


def test_text_the_engine_cannot_voice_is_a_422_and_does_not_silence_the_engine(speech):
    """"👍" alone gives a healthy Kokoro nothing to render. That is a 422 (the
    client stays silent), not a 501, and the very next reply is spoken by
    Kokoro again, not by the fallback voice."""
    def quiet_for_symbols(text, voice, speed):
        if not any(ch.isalnum() for ch in text):
            return iter([])
        return iter([("g", "p", np.array([0.0, 0.5, -0.5], dtype=np.float32))])

    def _synth_piper(text):
        raise _EngineMissing("Piper not found in PATH")

    speech.tts._kokoro_pipeline = quiet_for_symbols
    speech.tts._synth_piper = _synth_piper

    symbols = speech.client.post("/api/speech", json={"text": "👍"})
    assert symbols.status_code == 422
    assert "nothing in this text" in symbols.json()["detail"].lower()

    after = speech.client.post("/api/speech", json={"text": "All done."})
    assert after.status_code == 200 and after.content[:4] == b"RIFF"


def test_speech_works_again_after_a_failed_first_use_with_no_restart(speech):
    """The user-visible contract of the retry window: the first reply after
    install can fail (model download, no network) and be spoken by the
    client's fallback voice; a minute later SAM's own voice works."""
    now = [5000.0]
    speech.tts._clock = lambda: now[0]
    attempts = []

    def offline_then_online(text, voice, speed):
        attempts.append(text)
        if len(attempts) == 1:
            raise OSError("could not download the model: no network")
        return iter([("g", "p", np.array([0.0, 0.5, -0.5], dtype=np.float32))])

    def _synth_piper(text):
        raise _EngineMissing("Piper not found in PATH")

    speech.tts._kokoro_pipeline = offline_then_online
    speech.tts._synth_piper = _synth_piper

    first = speech.client.post("/api/speech", json={"text": "one"})
    assert first.status_code == 501 and "kokoro: failed" in first.json()["detail"]
    assert "could not download" not in first.json()["detail"]

    now[0] += 10
    assert speech.client.post("/api/speech", json={"text": "two"}).status_code == 501
    assert len(attempts) == 1  # answered at once; no second slow attempt

    now[0] += 60
    third = speech.client.post("/api/speech", json={"text": "three"})
    assert third.status_code == 200 and third.content[:4] == b"RIFF"
    assert len(attempts) == 2


def test_a_settings_change_applies_to_the_next_request(speech):
    """PATCH /api/settings mutates the one shared settings object in place;
    the next speech request must see it with no restart."""
    assert speech.client.post("/api/speech", json={"text": "one"}).status_code == 200
    speech.settings.kokoro_voice, speech.settings.speech_rate = "am_adam", 1.25
    assert speech.client.post("/api/speech", json={"text": "two"}).status_code == 200
    assert speech.kokoro.calls[-1] == ("two", "am_adam", 1.25)

    speech.settings.tts_engine = "none"
    assert speech.client.post("/api/speech", json={"text": "three"}).status_code == 409
    speech.settings.tts_engine = "kokoro"
    assert speech.client.post("/api/speech", json={"text": "four"}).status_code == 200


def test_get_tts_is_shared_and_follows_the_live_settings_object(monkeypatch):
    monkeypatch.setattr(server, "_tts", None)
    first_settings, second_settings = make_settings(), make_settings("piper")
    monkeypatch.setattr(server, "_gateway", SimpleNamespace(settings=first_settings))
    tts = server.get_tts()
    assert tts.settings is first_settings
    assert server.get_tts() is tts

    monkeypatch.setattr(server, "_gateway", SimpleNamespace(settings=second_settings))
    assert server.get_tts() is tts and tts.settings is second_settings


# ─── installing a speech engine takes effect without a restart ───────────

class FakeEnvironmentManager:
    """Replaces EnvironmentCompatibilityManager for POST /api/environment/repair."""
    outcome = None  # an exception to raise, or the dict to return

    def repair_dependencies(self, groups):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def test_successful_repair_makes_the_speech_engine_look_again(speech, monkeypatch):
    speech.tts._synth_failed_at["_synth_kokoro"] = speech.tts._clock()  # "Kokoro was missing"
    FakeEnvironmentManager.outcome = {"state": "complete", "groups": ["speech-output"]}
    monkeypatch.setattr(server, "EnvironmentCompatibilityManager", FakeEnvironmentManager)

    with patch("interfaces.api.server.importlib.invalidate_caches") as invalidate:
        response = speech.client.post("/api/environment/repair", json={"groups": ["speech-output"]})

    assert response.status_code == 200
    assert response.json() == {"state": "complete", "groups": ["speech-output"]}  # unchanged response
    invalidate.assert_called_once_with()
    fresh = server.get_tts()
    assert fresh is not speech.tts
    assert fresh._synth_failed_at == {}


def test_failed_repair_keeps_what_the_speech_engine_learned(speech, monkeypatch):
    from runtime.compatibility import CompatibilityError
    failed_at = speech.tts._clock()
    speech.tts._synth_failed_at["_synth_kokoro"] = failed_at
    FakeEnvironmentManager.outcome = CompatibilityError("pip failed")
    monkeypatch.setattr(server, "EnvironmentCompatibilityManager", FakeEnvironmentManager)

    response = speech.client.post("/api/environment/repair", json={"groups": ["speech-output"]})

    assert response.status_code == 422
    assert server.get_tts() is speech.tts
    assert speech.tts._synth_failed_at == {"_synth_kokoro": failed_at}


# ─── execution events can carry structured data ─────────────────────────

def test_event_without_data_keeps_exactly_its_original_shape():
    event = EventBus().publish("t1", "received", "Task received by SAM")
    assert set(event) == {"type", "task_id", "seq", "phase", "message", "timestamp"}


def test_event_data_is_copied_replayed_and_streamed_to_clients():
    bus = EventBus()
    payload = {"transcript": "open safari"}
    event = bus.publish("t1", "perceiving", "Heard your voice message", data=payload)
    payload["transcript"] = "mutated later"

    assert event["data"] == {"transcript": "open safari"}
    assert bus.get_since("t1", 0)[0]["data"] == {"transcript": "open safari"}  # reconnect replay
    frame = server._format_sse(event)
    assert json.loads(frame.split("data: ", 1)[1])["data"]["transcript"] == "open safari"


def test_empty_data_is_left_out_of_the_event():
    assert "data" not in EventBus().publish("t1", "planning", "Planning", data={})


# ─── gateway: the transcript reaches the client ─────────────────────────

@dataclass
class FakeBrainResponse:
    text: str
    action: str = None
    action_payload: dict = None


@pytest.fixture
def gateway(tmp_path, monkeypatch):
    from interfaces.api import task_store
    monkeypatch.setattr(task_store, "IQOO_DIR", tmp_path / "iqoo")
    monkeypatch.setattr(task_store, "TASKS_DB_PATH", tmp_path / "iqoo" / "tasks.db")
    with patch("memory.identity.Identity") as identity, \
         patch("memory.retrieve.MemoryRetriever") as memory, \
         patch("founder_mode.manager.FounderModeManager") as founder, \
         patch("core.brain.Brain") as brain, \
         patch("agent.react_loop.ReactLoop"), \
         patch("interfaces.api.gateway.VisionAdapter"), \
         patch("interfaces.api.gateway.AudioAdapter") as audio:
        identity.return_value.load.return_value = {}
        memory.return_value.retrieve.return_value = []
        memory.return_value.get_store.return_value = None
        founder.return_value.get_context.return_value = ""
        founder.return_value.capture_if_relevant.return_value = None
        brain.return_value._check_ollama.return_value = True
        brain.return_value.process.return_value = FakeBrainResponse(text="Done.")

        from config.settings import Settings
        settings = Settings()
        settings.incognito = True
        from interfaces.api.gateway import TaskGateway
        gw = TaskGateway(settings=settings)
    gw.audio = audio.return_value
    yield gw
    gw.shutdown()


def wait_for_status(gw, task_id, statuses, timeout=10.0):
    deadline = time.time() + timeout
    status = None
    while time.time() < deadline:
        status = gw.get_task(task_id)["status"]
        if status in statuses:
            return status
        time.sleep(0.05)
    return status


def heard_events(gw, task_id):
    return [e for e in gw.event_bus.get_since(task_id, 0) if "data" in e]


def test_voice_task_publishes_what_was_heard_before_the_brain_runs(gateway):
    gateway.audio.transcribe.return_value = "open safari and go to github"
    task_id = gateway.submit_task(
        "(voice command)", input_type="voice",
        attachments=[{"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV}])

    assert wait_for_status(gateway, task_id, {"completed", "failed"}) == "completed"
    events = gateway.event_bus.get_since(task_id, 0)
    heard = heard_events(gateway, task_id)
    assert len(heard) == 1
    assert heard[0]["phase"] == "perceiving"
    assert heard[0]["data"] == {"transcript": "open safari and go to github"}
    phases = [e["phase"] for e in events]
    assert phases.index("perceiving") < events.index(heard[0]) < phases.index("understanding")


def test_image_and_voice_task_also_publishes_what_was_heard(gateway):
    gateway.audio.transcribe.return_value = "what is on this screen"
    image = base64.b64encode(b"\xff\xd8\xff" + b"fake jpeg bytes for offline testing" * 4).decode()
    task_id = gateway.submit_task(
        "(voice command)", input_type="image+voice",
        attachments=[{"kind": "image", "mime_type": "image/jpeg", "data": image},
                     {"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV}])
    wait_for_status(gateway, task_id, {"completed", "failed"})
    assert [e["data"] for e in heard_events(gateway, task_id)] == [{"transcript": "what is on this screen"}]


def test_text_task_emits_no_data_events(gateway):
    task_id = gateway.submit_task("what time is it")
    assert wait_for_status(gateway, task_id, {"completed", "failed"}) == "completed"
    assert heard_events(gateway, task_id) == []


def test_failed_transcription_publishes_nothing_heard_and_fails_the_task(gateway):
    gateway.audio.transcribe.side_effect = PerceptionError("Transcription produced no text")
    task_id = gateway.submit_task(
        "(voice command)", input_type="voice",
        attachments=[{"kind": "audio", "mime_type": "audio/webm", "data": FAKE_WAV}])

    assert wait_for_status(gateway, task_id, {"completed", "failed"}) == "failed"
    assert heard_events(gateway, task_id) == []
    last = gateway.event_bus.get_since(task_id, 0)[-1]
    assert last["phase"] == "failed" and "Transcription produced no text" in last["message"]


# ─── audio adapter: first-use behaviour ─────────────────────────────────

class ScriptedSTT:
    """Stands in for ears.stt.SpeechToText; `script` decides what each
    _load_model() call does: an Exception to raise, True for a loaded model,
    False for "faster-whisper missing" (model stays None, as ears/stt.py does)."""
    script = []
    built = []

    def __init__(self, settings):
        ScriptedSTT.built.append(self)
        self._model = None
        self._model_loaded = False

    def _load_model(self):
        step = ScriptedSTT.script.pop(0)
        if isinstance(step, Exception):
            raise step
        self._model = object() if step else None
        self._model_loaded = True


@pytest.fixture
def scripted_stt(monkeypatch):
    ScriptedSTT.script, ScriptedSTT.built = [], []
    monkeypatch.setattr("ears.stt.SpeechToText", ScriptedSTT)
    return ScriptedSTT


def test_a_failed_model_load_is_not_cached_and_is_retried(scripted_stt):
    scripted_stt.script = [OSError("offline"), True]
    adapter = AudioAdapter(make_settings())

    with pytest.raises(OSError):
        adapter._get_stt()
    assert adapter._stt is None  # no half-built instance remembered

    stt = adapter._get_stt()  # the network is back
    assert stt._model is not None
    assert adapter._get_stt() is stt
    assert len(scripted_stt.built) == 2


def test_a_model_load_failure_is_reported_as_a_perception_error_with_advice(scripted_stt):
    scripted_stt.script = [OSError("could not reach huggingface.co")]
    adapter = AudioAdapter(make_settings())

    with pytest.raises(PerceptionError) as failure:
        adapter.transcribe({"mime_type": "audio/webm", "data": FAKE_WAV})
    message = str(failure.value)
    assert "speech model" in message
    assert "could not reach huggingface.co" in message
    assert "internet connection" in message


def test_bad_audio_is_still_rejected_before_any_model_is_loaded(scripted_stt):
    adapter = AudioAdapter(make_settings())
    with pytest.raises(PerceptionError, match="decode"):
        adapter.transcribe({"mime_type": "audio/webm", "data": "not valid base64 at all!!"})
    assert scripted_stt.built == []


def test_faster_whisper_installed_later_is_picked_up_without_a_restart(scripted_stt, monkeypatch):
    installed = {"yes": False}
    monkeypatch.setattr(AudioAdapter, "whisper_installed", staticmethod(lambda: installed["yes"]))
    scripted_stt.script = [False, True]  # first build: package missing; second build: model loads
    adapter = AudioAdapter(make_settings())

    before = adapter._get_stt()
    assert before._model is None
    assert adapter._get_stt() is before  # still not installed: keep it, do not rebuild every call

    installed["yes"] = True  # Diagnostics -> "Install speech-input" finished
    after = adapter._get_stt()
    assert after is not before and after._model is not None
    assert adapter._get_stt() is after  # a loaded model is never rebuilt
