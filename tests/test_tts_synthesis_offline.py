"""
Voice Phase A — mouth/tts.py: synthesize_wav() and the Kokoro/Piper
refactor behind it.

Offline: no TTS engine, audio device, or model is touched. Kokoro is a fake
pipeline object and Piper is a fake subprocess, so these prove the contract
(WAV format, text cleaning, fallback order, a failed engine being left alone
and then retried, the disabled/unavailable errors, locking) and that speak() still renders and
plays exactly what it did before the refactor. They do NOT prove that real
Kokoro/Piper produce good audio on a real machine.

Plain pytest functions on purpose: CI runs `pytest tests`, which silently
collects zero tests from the script-style suites in this directory.
"""

import io
import os
import sys
import threading
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mouth.tts as tts_module  # noqa: E402
from mouth.tts import (  # noqa: E402
    KOKORO_SAMPLE_RATE, SYNTH_RETRY_SECONDS, TextToSpeech, TTSDisabledError, TTSUnavailableError,
    _EngineMissing,
)


def make_settings(engine="kokoro"):
    return SimpleNamespace(tts_engine=engine, kokoro_voice="af_bella",
                           speech_rate=1.0, piper_model="en_US-lessac-medium")


class FakeClock:
    """A clock the test moves by hand (TextToSpeech._clock is replaceable)."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeKokoro:
    """Stands in for kokoro.KPipeline: yields (graphemes, phonemes, audio)."""

    def __init__(self, chunks, delay=0.0):
        self.chunks = chunks
        self.delay = delay
        self.calls = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()

    def __call__(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                time.sleep(self.delay)
            return iter([("g", "p", chunk) for chunk in self.chunks])
        finally:
            with self._lock:
                self.active -= 1


class BrokenKokoro:
    """A Kokoro pipeline that raises when used: a real engine fault, with an
    error text that holds a file path (it must never reach API callers)."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        raise RuntimeError("model file /home/someone/.cache/kokoro.pt is corrupt")


class SymbolDeaf:
    """A Kokoro pipeline that works but has nothing to voice for text with no
    letters or digits in it ("👍", "...") -- it yields no audio for those."""

    def __init__(self):
        self.calls = []

    def __call__(self, text, voice, speed):
        self.calls.append((text, voice, speed))
        if not any(ch.isalnum() for ch in text):
            return iter([])
        return iter([("g", "p", np.array([0.2], dtype=np.float32))])


def tts_with_kokoro(chunks, engine="kokoro", delay=0.0):
    tts = TextToSpeech(make_settings(engine))
    tts._kokoro_pipeline = FakeKokoro(chunks, delay=delay)
    tts._kokoro_loaded = True
    return tts


def tts_with_pipeline(pipeline, engine="kokoro"):
    tts = TextToSpeech(make_settings(engine))
    tts._kokoro_pipeline, tts._kokoro_loaded = pipeline, True
    return tts


def read_wav(data):
    with wave.open(io.BytesIO(data)) as wav:
        return (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(),
                np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2"))


# ─── WAV output ──────────────────────────────────────────────────────────

def test_synthesize_wav_returns_mono_16bit_wav_at_kokoro_rate():
    chunks = [np.array([0.0, 0.5, -0.5], dtype=np.float32),
              np.array([1.0, -1.0, 2.0], dtype=np.float32)]  # 2.0 must clip, not wrap
    data = tts_with_kokoro(chunks).synthesize_wav("Hello there")

    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    channels, width, rate, samples = read_wav(data)
    assert KOKORO_SAMPLE_RATE == 24000
    assert (channels, width, rate) == (1, 2, 24000)
    assert samples.tolist() == [0, 16383, -16383, 32767, -32767, 32767]


def test_chunks_are_joined_in_order_and_empty_chunks_ignored():
    chunks = [np.array([0.1, 0.2], dtype=np.float32), None,
              np.array([], dtype=np.float32), np.array([0.3], dtype=np.float32)]
    _, _, _, samples = read_wav(tts_with_kokoro(chunks).synthesize_wav("one two"))
    assert samples.tolist() == [int(0.1 * 32767), int(0.2 * 32767), int(0.3 * 32767)]


def test_text_is_cleaned_for_speech_and_voice_settings_are_passed_through():
    tts = tts_with_kokoro([np.array([0.1], dtype=np.float32)])
    tts.synthesize_wav("**Done.** Ran `ls`.\n- one\n- two")
    text, voice, speed = tts._kokoro_pipeline.calls[0]
    assert "*" not in text and "`" not in text and "\n" not in text
    assert text.startswith("Done. Ran ls.")
    assert (voice, speed) == ("af_bella", 1.0)


def test_empty_or_blank_text_raises_value_error_without_touching_an_engine():
    tts = tts_with_kokoro([np.array([0.1], dtype=np.float32)])
    for blank in ("", "   ", "\n\t"):
        with pytest.raises(ValueError):
            tts.synthesize_wav(blank)
    assert tts._kokoro_pipeline.calls == []


# ─── engine selection and failure handling ───────────────────────────────

def test_speech_off_and_system_voice_are_distinguished_from_missing_engines():
    with pytest.raises(TTSDisabledError) as off:
        TextToSpeech(make_settings("none")).synthesize_wav("hi")
    assert off.value.code == "speech_disabled"
    assert isinstance(off.value, TTSUnavailableError)  # callers can catch the base

    with pytest.raises(TTSUnavailableError) as system:
        TextToSpeech(make_settings("system")).synthesize_wav("hi")
    assert not isinstance(system.value, TTSDisabledError)
    assert system.value.code == "tts_engine_unavailable"


def test_kokoro_failure_falls_back_to_piper_and_is_left_alone_until_the_retry_time():
    tts = tts_with_pipeline(BrokenKokoro())
    clock = tts._clock = FakeClock()
    piper_calls = []

    def _synth_piper(text):
        piper_calls.append(text)
        return b"RIFF-from-piper"

    tts._synth_piper = _synth_piper
    assert tts.synthesize_wav("hello") == b"RIFF-from-piper"
    assert "_synth_kokoro" in tts._synth_failed_at
    assert tts._known_bad_engines == set()  # speak()'s own memory is separate and untouched

    kokoro_calls = len(tts._kokoro_pipeline.calls)
    clock.advance(SYNTH_RETRY_SECONDS - 1)
    assert tts.synthesize_wav("again") == b"RIFF-from-piper"
    assert len(tts._kokoro_pipeline.calls) == kokoro_calls  # one second short: not retried

    clock.advance(1)  # exactly the retry time
    assert tts.synthesize_wav("later") == b"RIFF-from-piper"
    assert len(tts._kokoro_pipeline.calls) == kokoro_calls + 1  # tried again (and failed again)
    assert piper_calls == ["hello", "again", "later"]


def test_a_failed_first_use_download_is_retried_and_then_forgiven(caplog):
    """Kokoro's first use downloads a model. Offline, that raises; when the
    network is back, SAM's voice must work again with no restart."""
    clock = FakeClock()
    attempts = []

    def offline_then_online(text, voice, speed):
        attempts.append(text)
        if len(attempts) == 1:
            raise OSError("could not download the model: no network")
        return iter([("g", "p", np.array([0.25], dtype=np.float32))])

    def _synth_piper(text):
        raise _EngineMissing("Piper not found in PATH")

    tts = TextToSpeech(make_settings("kokoro"))
    tts._clock = clock
    tts._kokoro_pipeline, tts._kokoro_loaded = offline_then_online, True
    tts._synth_piper = _synth_piper

    with caplog.at_level("WARNING", logger="SAM.TTS"):
        with pytest.raises(TTSUnavailableError) as offline:
            tts.synthesize_wav("first")
    # The caller gets a fixed reason; the real error text goes to the log.
    assert "kokoro: failed;" in str(offline.value)
    assert "could not download the model" not in str(offline.value)
    assert "could not download the model: no network" in caplog.text

    clock.advance(5)
    with pytest.raises(TTSUnavailableError) as soon:
        tts.synthesize_wav("second")
    assert "kokoro: failed 5 s ago" in str(soon.value)
    assert len(attempts) == 1  # no second slow download attempt inside the window

    clock.advance(SYNTH_RETRY_SECONDS)
    _, _, _, samples = read_wav(tts.synthesize_wav("third"))
    assert samples.tolist() == [int(0.25 * 32767)]
    assert len(attempts) == 2
    assert "_synth_kokoro" not in tts._synth_failed_at  # forgiven once it worked


def test_piper_first_when_configured():
    tts = tts_with_kokoro([np.array([0.1], dtype=np.float32)], engine="piper")

    # Named like the real method so known-bad tracking (keyed by __name__)
    # behaves as it would in production.
    def _synth_piper(text):
        return b"RIFF-piper-first"

    tts._synth_piper = _synth_piper
    assert tts.synthesize_wav("hello") == b"RIFF-piper-first"
    assert tts._kokoro_pipeline.calls == []


def test_all_engines_failing_raises_unavailable_naming_every_failure():
    tts = TextToSpeech(make_settings("kokoro"))  # no pipeline loaded, kokoro absent
    clock = tts._clock = FakeClock()
    attempts = []

    def _synth_kokoro(text):
        attempts.append("kokoro")
        raise _EngineMissing("Kokoro not available")

    def _synth_piper(text):
        attempts.append("piper")
        raise _EngineMissing("Piper not found in PATH")

    tts._synth_kokoro, tts._synth_piper = _synth_kokoro, _synth_piper
    with pytest.raises(TTSUnavailableError) as failure:
        tts.synthesize_wav("hello")
    message = str(failure.value)
    assert "kokoro: not installed" in message
    assert "piper: not installed" in message
    assert not isinstance(failure.value, TTSDisabledError)

    # Both failed just now: a second request fails fast without retrying them.
    with pytest.raises(TTSUnavailableError) as again:
        tts.synthesize_wav("hello again")
    assert "kokoro: failed 0 s ago" in str(again.value) and "piper: failed 0 s ago" in str(again.value)
    assert attempts == ["kokoro", "piper"]

    # After the retry time both are tried again.
    clock.advance(SYNTH_RETRY_SECONDS)
    with pytest.raises(TTSUnavailableError):
        tts.synthesize_wav("hello later")
    assert attempts == ["kokoro", "piper", "kokoro", "piper"]


def test_synthesis_is_serialised_across_threads():
    tts = tts_with_kokoro([np.array([0.1], dtype=np.float32)], delay=0.05)
    errors = []

    def run():
        try:
            tts.synthesize_wav("hello")
        except Exception as exc:  # pragma: no cover - would fail the assert below
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert errors == []
    assert tts._kokoro_pipeline.max_active == 1


# ─── Piper rendering ─────────────────────────────────────────────────────

def wav_bytes(samples, rate=22050):
    return TextToSpeech._pcm16_wav(np.asarray(samples, dtype=np.float32), rate)


WAV_BYTES = wav_bytes([0.1, -0.1, 0.2])  # a real (tiny) WAV: Piper's file is checked, then returned verbatim
EMPTY_WAV = wav_bytes([])  # a WAV header and no sound


def fake_piper_subprocess(record, wav=WAV_BYTES, error=None):
    def run(cmd, input=None, capture_output=None, check=None, timeout=None):
        out_path = cmd[cmd.index("--output_file") + 1]
        record["cmd"], record["input"], record["out_path"] = cmd, input, out_path
        if error is not None:
            raise error
        with open(out_path, "wb") as handle:
            handle.write(wav)
        return SimpleNamespace(returncode=0)
    return SimpleNamespace(run=run)


def piper_only(monkeypatch, record, **fake):
    """Piper first, through the real _synth_piper with a fake subprocess;
    Kokoro is "not installed"."""
    monkeypatch.setattr(tts_module, "subprocess", fake_piper_subprocess(record, **fake))
    monkeypatch.setattr("shutil.which", lambda name: "/opt/piper-secret/bin/piper")
    tts = TextToSpeech(make_settings("piper"))
    tts._kokoro_loaded = True  # skip the kokoro attempt entirely
    tts._kokoro_pipeline = None
    tts._clock = FakeClock()
    return tts


def test_synth_piper_returns_the_rendered_file_and_cleans_up(monkeypatch):
    record = {}
    monkeypatch.setattr(tts_module, "subprocess", fake_piper_subprocess(record))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/piper")

    tts = TextToSpeech(make_settings("piper"))
    tts._kokoro_loaded = True  # skip the kokoro attempt entirely
    tts._kokoro_pipeline = None
    assert tts.synthesize_wav("hello there") == WAV_BYTES
    assert record["cmd"][:3] == ["/usr/local/bin/piper", "--model", "en_US-lessac-medium"]
    assert record["input"] == b"hello there"
    assert not os.path.exists(record["out_path"])


def test_missing_piper_binary_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    tts = TextToSpeech(make_settings("piper"))
    tts._kokoro_loaded = True
    tts._kokoro_pipeline = None
    with pytest.raises(TTSUnavailableError) as failure:
        tts.synthesize_wav("hello")
    # Piper was the configured first choice; Kokoro was tried after it.
    assert "piper: not installed" in str(failure.value)
    assert "kokoro: not installed" in str(failure.value)


# ─── what an engine failure tells the caller ─────────────────────────────

def test_a_piper_crash_does_not_leak_paths_or_command_lines_to_the_caller(monkeypatch, caplog):
    import subprocess as real_subprocess
    record = {}
    crash = real_subprocess.CalledProcessError(
        1, ["/opt/piper-secret/bin/piper", "--model", "en_US-lessac-medium",
            "--output_file", "/tmp/tmpq4rel8ov.wav"])
    tts = piper_only(monkeypatch, record, error=crash)

    with caplog.at_level("WARNING", logger="SAM.TTS"):
        with pytest.raises(TTSUnavailableError) as failure:
            tts.synthesize_wav("hello")
    message = str(failure.value)
    assert "piper: failed" in message
    for leaked in ("/opt/piper-secret", "/tmp/", ".wav", "--model", "returned non-zero"):
        assert leaked not in message
    assert "/opt/piper-secret/bin/piper" in caplog.text  # the full error is in the server log
    assert not os.path.exists(record["out_path"])


def test_a_piper_timeout_is_reported_as_timed_out(monkeypatch):
    import subprocess as real_subprocess
    record = {}
    tts = piper_only(monkeypatch, record,
                     error=real_subprocess.TimeoutExpired(["/opt/piper-secret/bin/piper"], 30))
    with pytest.raises(TTSUnavailableError) as failure:
        tts.synthesize_wav("hello")
    assert "piper: timed out" in str(failure.value)
    assert "/opt/piper-secret" not in str(failure.value)
    assert "_synth_piper" in tts._synth_failed_at  # a hung engine IS left alone for a while


def test_a_piper_file_that_is_not_a_wav_is_an_engine_failure(monkeypatch):
    record = {}
    tts = piper_only(monkeypatch, record, wav=b"this is not a wav file at all")
    with pytest.raises(TTSUnavailableError) as failure:
        tts.synthesize_wav("hello")
    assert "piper: failed" in str(failure.value)
    assert "_synth_piper" in tts._synth_failed_at
    assert not os.path.exists(record["out_path"])


# ─── text an engine has nothing to say for is not an engine failure ──────

@pytest.mark.parametrize("silent_file", [b"", EMPTY_WAV], ids=["empty file", "header only"])
def test_a_silent_piper_file_means_nothing_to_say_and_does_not_silence_piper(monkeypatch, silent_file):
    record = {}
    tts = piper_only(monkeypatch, record, wav=silent_file)
    with pytest.raises(ValueError) as nothing:
        tts.synthesize_wav("...")
    assert not isinstance(nothing.value, TTSUnavailableError)  # the route's 422, not its 501
    assert "_synth_piper" not in tts._synth_failed_at
    assert not os.path.exists(record["out_path"])


def test_text_kokoro_cannot_voice_is_nothing_to_say_and_does_not_silence_kokoro():
    """A reply that is only symbols ("👍") makes a healthy Kokoro yield no
    audio. That must not put Kokoro in the cooldown: the next, ordinary reply
    has to be spoken by Kokoro, not by a fallback voice."""
    tts = tts_with_pipeline(SymbolDeaf())
    clock = tts._clock = FakeClock()

    def _synth_piper(text):
        raise _EngineMissing("Piper not found in PATH")

    tts._synth_piper = _synth_piper
    with pytest.raises(ValueError) as nothing:
        tts.synthesize_wav("👍")
    assert not isinstance(nothing.value, TTSUnavailableError)
    assert "_synth_kokoro" not in tts._synth_failed_at
    assert "_synth_piper" in tts._synth_failed_at  # Piper really is missing

    clock.advance(5)
    _, _, _, samples = read_wav(tts.synthesize_wav("good morning"))
    assert samples.tolist() == [int(0.2 * 32767)]
    assert [call[0] for call in tts._kokoro_pipeline.calls] == ["👍", "good morning"]


def test_when_kokoro_has_nothing_to_say_piper_still_gets_its_turn():
    tts = tts_with_pipeline(SymbolDeaf())
    tts._clock = FakeClock()

    def _synth_piper(text):
        return b"RIFF-from-piper"

    tts._synth_piper = _synth_piper
    assert tts.synthesize_wav("...") == b"RIFF-from-piper"
    assert tts._synth_failed_at == {}


def test_an_engine_that_failed_before_and_now_runs_is_forgiven_even_with_nothing_to_say():
    clock = FakeClock()
    attempts = []

    def pipeline(text, voice, speed):
        attempts.append(text)
        if len(attempts) == 1:
            raise OSError("offline")
        return iter([])  # runs fine, says nothing

    def _synth_piper(text):
        raise _EngineMissing("Piper not found in PATH")

    tts = tts_with_pipeline(pipeline)
    tts._clock = clock
    tts._synth_piper = _synth_piper
    with pytest.raises(TTSUnavailableError):
        tts.synthesize_wav("first")
    assert "_synth_kokoro" in tts._synth_failed_at

    clock.advance(SYNTH_RETRY_SECONDS)
    with pytest.raises(ValueError):
        tts.synthesize_wav("second")  # Kokoro ran: nothing to say, and no longer "failed"
    assert "_synth_kokoro" not in tts._synth_failed_at


# ─── speak() is unchanged by the refactor ────────────────────────────────

def test_speak_still_renders_kokoro_and_plays_it_through_the_speakers(monkeypatch):
    chunks = [np.array([0.1, 0.2], dtype=np.float32), np.array([0.3], dtype=np.float32)]
    tts = tts_with_kokoro(chunks)
    played = []
    monkeypatch.setattr(tts, "_play_audio_array", lambda audio, rate: played.append((audio, rate)))
    tts.speak("**Hello** world")

    assert len(played) == 1
    audio, rate = played[0]
    assert rate == 24000
    assert audio.dtype == np.float32
    assert audio.tolist() == pytest.approx([0.1, 0.2, 0.3])
    assert tts._kokoro_pipeline.calls[0][0] == "Hello world"


def test_speak_still_plays_a_piper_file_then_deletes_it(monkeypatch):
    record = {}
    monkeypatch.setattr(tts_module, "subprocess", fake_piper_subprocess(record))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/piper")
    tts = TextToSpeech(make_settings("piper"))
    seen = {}

    def play(path):
        seen["path"] = path
        seen["existed"] = os.path.exists(path)

    monkeypatch.setattr(tts, "_play_audio_file", play)
    tts.speak("hello")
    assert seen["existed"] is True
    assert seen["path"] == record["out_path"]
    assert not os.path.exists(seen["path"])


def test_engine_order_for_speaking_is_unchanged():
    assert [e.__name__ for e in TextToSpeech(make_settings("kokoro"))._get_engine_order()] == \
        ["_speak_kokoro", "_speak_piper", "_speak_system"]
    assert [e.__name__ for e in TextToSpeech(make_settings("piper"))._get_engine_order()] == \
        ["_speak_piper", "_speak_kokoro", "_speak_system"]
    assert [e.__name__ for e in TextToSpeech(make_settings("none"))._get_engine_order()] == ["_speak_print"]
