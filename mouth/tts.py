"""
THE MOUTH — Text to Speech
Cross-platform: macOS + Windows

Primary:  Kokoro TTS (82M params, Apache 2.0, best quality)
Fallback: Piper TTS (fastest, MIT)
Last resort: macOS `say` or Windows `pyttsx3`
"""

import io
import logging
import os
import tempfile
import subprocess
import platform
import threading
import time
import wave
from subprocess import TimeoutExpired

logger = logging.getLogger("SAM.TTS")

PLATFORM = platform.system()
IS_MAC = PLATFORM == "Darwin"
IS_WIN = PLATFORM == "Windows"

KOKORO_SAMPLE_RATE = 24000

# How long synthesize_wav() leaves an engine alone after it failed. Long
# enough that a missing or offline engine costs one slow attempt, not one per
# reply; short enough that a first-use model download that failed (no
# network) is tried again soon after the network is back, with no restart.
SYNTH_RETRY_SECONDS = 60.0


class TTSUnavailableError(RuntimeError):
    """synthesize_wav() could not render audio bytes: no installed engine
    (Kokoro, Piper) worked, or the configured engine is one that only plays
    through the local speakers (the "system" voice). The caller can fall
    back to a voice of its own (the desktop app falls back to the webview's
    speech synthesis)."""
    code = "tts_engine_unavailable"


class TTSDisabledError(TTSUnavailableError):
    """The user turned speech output off (tts_engine: none). Callers must
    stay silent rather than fall back to another voice."""
    code = "speech_disabled"


# The two private errors below are RuntimeErrors with the messages they always
# had, so speak() (which catches Exception) treats them exactly as before.
# synthesize_wav() tells them apart from a real engine fault.

class _EngineMissing(RuntimeError):
    """The engine is not installed (the Kokoro package, the piper program)."""


class _NoAudio(RuntimeError):
    """The engine ran fine but made no sound for this text (a reply that is
    only symbols, say). That is the text's doing, not the engine's, so
    synthesize_wav() must not leave the engine alone because of it."""


class TextToSpeech:
    def __init__(self, settings):
        self.settings = settings
        self._kokoro_pipeline = None
        self._kokoro_loaded = False
        self._pyttsx3_engine = None
        # synthesize_wav() can be called from several API worker threads;
        # Kokoro's pipeline and the first-use model load are not something
        # to run concurrently.
        self._synth_lock = threading.Lock()
        # Latency fix: engines that fail once are skipped for the rest of
        # this run instead of being retried every single turn. In real
        # testing, Kokoro/Piper failing-then-falling-through was costing
        # ~10+ seconds of wasted retry time on every response. Clears
        # naturally on restart, so fixing the underlying issue (e.g.
        # installing Piper) takes effect next run.
        self._known_bad_engines = set()
        # synthesize_wav() keeps its own, shorter memory: engine name -> when
        # it last failed, by self._clock(). speak() keeps the rest-of-the-run
        # rule above. The desktop app's first use downloads a model, and a
        # download that failed while offline must not silence SAM's voice
        # until the app is restarted. (The clock is replaceable for tests.)
        self._synth_failed_at = {}
        self._clock = time.monotonic
        logger.info(f"TTS initialised for platform: {PLATFORM}")

    def speak(self, text: str):
        if not text or not text.strip():
            return
        text = self._clean_for_speech(text)
        logger.info(f"Speaking: {text[:80]}...")

        for engine in self._get_engine_order():
            if engine.__name__ in self._known_bad_engines:
                continue
            try:
                engine(text)
                return
            except Exception as e:
                logger.warning(f"TTS engine failed ({engine.__name__}): {e} "
                                f"— skipping it for the rest of this session")
                self._known_bad_engines.add(engine.__name__)

        self._speak_print(text)

    def _get_engine_order(self):
        engine_name = getattr(self.settings, "tts_engine", "kokoro")
        if engine_name == "kokoro":
            return [self._speak_kokoro, self._speak_piper, self._speak_system]
        elif engine_name == "piper":
            return [self._speak_piper, self._speak_kokoro, self._speak_system]
        elif engine_name == "system":
            return [self._speak_system]
        elif engine_name == "none":
            return [self._speak_print]
        return [self._speak_kokoro, self._speak_piper, self._speak_system]

    # ─── Synthesis to bytes (voice Phase A) ───────────────────────────────
    #
    # speak() renders AND plays through this machine's speakers, which is
    # what the legacy main.py voice process wants. The desktop app instead
    # records and plays audio inside its own webview, so it needs the audio
    # as data: synthesize_wav() returns a complete WAV file. speak() and
    # everything it calls behave exactly as before.

    def synthesize_wav(self, text: str) -> bytes:
        """Render `text` to a mono 16-bit WAV file and return its bytes.

        Raises ValueError when there is nothing to speak (empty text, or text
        that no working engine can turn into sound), TTSDisabledError when
        speech is switched off (tts_engine: none), and TTSUnavailableError
        when no engine that can produce audio bytes works (Kokoro and Piper
        are the two; the "system" voice only plays through the speakers). An
        engine that fails is left alone for SYNTH_RETRY_SECONDS and then tried
        again (speak() skips a failed engine for the rest of the run instead);
        an engine that merely had nothing to say for this text is not. The
        message of TTSUnavailableError names each engine with a fixed reason
        only: the full error (it can hold file paths and command lines) goes
        to the log, not to API callers.
        """
        if not text or not text.strip():
            raise ValueError("Nothing to speak")
        engines = self._get_synthesis_engine_order()
        cleaned = self._clean_for_speech(text)
        if not cleaned:
            raise ValueError("Nothing to speak")

        failures = []
        nothing_to_say = False
        with self._synth_lock:
            for engine in engines:
                name = engine.__name__
                label = name.replace("_synth_", "")
                failed_at = self._synth_failed_at.get(name)
                if failed_at is not None:
                    ago = self._clock() - failed_at
                    if ago < SYNTH_RETRY_SECONDS:
                        failures.append(f"{label}: failed {int(ago)} s ago (tries again after "
                                        f"{int(SYNTH_RETRY_SECONDS)} s)")
                        continue
                try:
                    wav = engine(cleaned)
                except _NoAudio:
                    # The engine works; this text gave it nothing to voice.
                    # It ran, so whatever failed it before is over.
                    self._synth_failed_at.pop(name, None)
                    nothing_to_say = True
                    failures.append(f"{label}: no audio for this text")
                    continue
                except (Exception, SystemExit) as e:
                    logger.warning(f"TTS synthesis engine failed ({name}): {e} "
                                   f"— leaving it alone for {int(SYNTH_RETRY_SECONDS)} s")
                    self._synth_failed_at[name] = self._clock()
                    failures.append(f"{label}: {self._failure_reason(e)}")
                    continue
                self._synth_failed_at.pop(name, None)
                return wav
        if nothing_to_say:
            raise ValueError("Nothing in this text that SAM's voice can say")
        raise TTSUnavailableError(
            "No installed speech engine could render audio (" + "; ".join(failures) + ").")

    @staticmethod
    def _failure_reason(error: Exception) -> str:
        """A short fixed phrase for an engine failure, safe to send to API
        callers (the real error text can hold paths and command lines)."""
        if isinstance(error, _EngineMissing):
            return "not installed"
        if isinstance(error, TimeoutExpired):
            return "timed out"
        return "failed"

    def _get_synthesis_engine_order(self):
        engine_name = getattr(self.settings, "tts_engine", "kokoro")
        if engine_name == "none":
            raise TTSDisabledError("Speech output is turned off (tts_engine: none).")
        if engine_name == "system":
            raise TTSUnavailableError(
                "The system voice can only play through this machine's speakers; "
                "it cannot return audio.")
        if engine_name == "piper":
            return [self._synth_piper, self._synth_kokoro]
        return [self._synth_kokoro, self._synth_piper]

    def _synth_system(self, text: str) -> bytes:
        """Synthesize text to WAV using OS built-in speech (say on macOS, SAPI on Windows)."""
        if IS_MAC:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tmp_path = tf.name
            try:
                rate_flag = []
                speed = getattr(self.settings, "speech_rate", 1.0)
                if speed and speed != 1.0:
                    rate_flag = ["-r", str(int(175 * speed))]
                subprocess.run(
                    ["/usr/bin/say", "-o", tmp_path, "--data-format=LEI16@24000", *rate_flag, text],
                    check=True,
                    capture_output=True,
                    timeout=10.0
                )
                with open(tmp_path, "rb") as f:
                    data = f.read()
                if not data:
                    raise _NoAudio("System speech produced 0 bytes")
                return data
            except Exception as e:
                raise RuntimeError(f"macOS say synthesis failed: {e}") from e
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        elif IS_WIN:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                tmp_path = tf.name
            try:
                ps_script = f"""
                Add-Type -AssemblyName System.Speech
                $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
                $synth.SetOutputToWaveFile('{tmp_path}')
                $synth.Speak('{text.replace("'", "''")}')
                $synth.Dispose()
                """
                subprocess.run(["powershell", "-Command", ps_script], check=True, capture_output=True, timeout=10.0)
                with open(tmp_path, "rb") as f:
                    data = f.read()
                if not data:
                    raise _NoAudio("Windows SAPI produced 0 bytes")
                return data
            except Exception as e:
                raise RuntimeError(f"Windows speech synthesis failed: {e}") from e
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        raise _EngineMissing("System speech synthesis not supported on this OS")

    @staticmethod
    def _pcm16_wav(samples, sample_rate: int) -> bytes:
        """float32 samples in [-1, 1] -> mono 16-bit PCM WAV bytes."""
        import numpy as np
        pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(sample_rate)
            out.writeframes(pcm.tobytes())
        return buffer.getvalue()

    # ─── Kokoro ───────────────────────────────────────────────────────────

    def _kokoro_render(self, text: str):
        """Run Kokoro and return the whole utterance as one float32 array."""
        if not self._kokoro_loaded:
            self._load_kokoro()
        if self._kokoro_pipeline is None:
            raise _EngineMissing("Kokoro not available")

        import numpy as np
        voice = getattr(self.settings, "kokoro_voice", "af_bella")
        speed = getattr(self.settings, "speech_rate", 1.0)

        audio_chunks = []
        for result in self._kokoro_pipeline(text, voice=voice, speed=speed):
            # Kokoro yields Result objects with .audio (torch.Tensor) or (graphemes, phonemes, audio) tuples
            if hasattr(result, "audio"):
                chunk = result.audio
            elif isinstance(result, (tuple, list)):
                chunk = result[-1]
            else:
                chunk = result

            if chunk is None:
                continue

            # Ensure it's a proper 1D numpy array
            try:
                if hasattr(chunk, "cpu"):
                    chunk = chunk.cpu()
                if hasattr(chunk, "numpy"):
                    chunk = chunk.numpy()
                chunk = np.array(chunk, dtype=np.float32).flatten()
                if chunk.size > 0:
                    audio_chunks.append(chunk)
            except Exception:
                continue

        if not audio_chunks:
            raise _NoAudio("Kokoro produced no audio")

        return np.concatenate(audio_chunks)

    def _speak_kokoro(self, text: str):
        self._play_audio_array(self._kokoro_render(text), KOKORO_SAMPLE_RATE)

    def _synth_kokoro(self, text: str) -> bytes:
        return self._pcm16_wav(self._kokoro_render(text), KOKORO_SAMPLE_RATE)

    def _load_kokoro(self):
        try:
            from kokoro import KPipeline
            self._kokoro_pipeline = KPipeline(lang_code="a")
            self._kokoro_loaded = True
            logger.info("Kokoro TTS loaded")
        except ImportError:
            logger.warning("Kokoro not installed")
            self._kokoro_loaded = True
            self._kokoro_pipeline = None

    # ─── Piper ────────────────────────────────────────────────────────────

    def _piper_render(self, text: str, out_path: str):
        """Run the piper binary, writing a WAV file to out_path."""
        import shutil
        piper_cmd = shutil.which("piper")
        if not piper_cmd:
            raise _EngineMissing("Piper not found in PATH")

        model = getattr(self.settings, "piper_model", "en_US-lessac-medium")
        subprocess.run(
            [piper_cmd, "--model", model, "--output_file", out_path],
            input=text.encode(),
            capture_output=True,
            check=True,
            timeout=30
        )

    def _speak_piper(self, text: str):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self._piper_render(text, tmp_path)
            self._play_audio_file(tmp_path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _synth_piper(self, text: str) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self._piper_render(text, tmp_path)
            with open(tmp_path, "rb") as rendered:
                data = rendered.read()
            if not data:
                raise _NoAudio("Piper produced no audio")
            try:
                with wave.open(io.BytesIO(data), "rb") as rendered_wav:
                    frames = rendered_wav.getnframes()
            except (wave.Error, EOFError) as e:
                raise RuntimeError("Piper wrote a file that is not a readable WAV") from e
            if frames == 0:  # a header and no sound
                raise _NoAudio("Piper produced no audio")
            return data
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ─── System TTS ───────────────────────────────────────────────────────

    def _speak_system(self, text: str):
        if os.environ.get("SAM_TEST_MODE") == "1":
            return
        if IS_MAC:
            subprocess.run(["say", text], timeout=60, check=True)
        elif IS_WIN:
            self._speak_pyttsx3(text)
        else:
            raise RuntimeError("No system TTS on this platform")

    def _speak_pyttsx3(self, text: str):
        if os.environ.get("SAM_TEST_MODE") == "1":
            return
        if self._pyttsx3_engine is None:
            import pyttsx3
            self._pyttsx3_engine = pyttsx3.init()
        self._pyttsx3_engine.say(text)
        self._pyttsx3_engine.runAndWait()

    def _speak_print(self, text: str):
        print(f"\n[SAM]: {text}\n")

    # ─── Audio Playback ───────────────────────────────────────────────────

    def _play_audio_array(self, audio, sample_rate: int):
        if os.environ.get("SAM_TEST_MODE") == "1":
            return
        try:
            import sounddevice as sd
            sd.play(audio, sample_rate)
            sd.wait()
            return
        except Exception as e:
            logger.warning(f"sounddevice failed: {e}")

        try:
            import soundfile as sf
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                sf.write(tmp.name, audio, sample_rate)
                self._play_audio_file(tmp.name)
                os.unlink(tmp.name)
        except Exception as e:
            raise RuntimeError(f"Audio playback failed: {e}")

    def _play_audio_file(self, path: str):
        if os.environ.get("SAM_TEST_MODE") == "1":
            return
        if IS_MAC:
            subprocess.run(["afplay", path], timeout=120, check=True)
        elif IS_WIN:
            try:
                ps_cmd = f'$p=New-Object System.Media.SoundPlayer("{path}");$p.PlaySync()'
                subprocess.run(["powershell", "-Command", ps_cmd], timeout=120, check=True, capture_output=True)
            except Exception:
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            for cmd in [["aplay", path], ["paplay", path]]:
                try:
                    subprocess.run(cmd, timeout=120, check=True, capture_output=True)
                    return
                except Exception:
                    continue

    # ─── Text Cleaning ────────────────────────────────────────────────────

    def _clean_for_speech(self, text: str) -> str:
        import re
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'#{1,6}\s', '', text)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        text = re.sub(r'^[\-\*]\s', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\d+\.\s', '', text, flags=re.MULTILINE)
        text = re.sub(r'\n+', '. ', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
