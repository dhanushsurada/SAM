"""
THE EARS — Part 1: Wake Word Detection
Uses openWakeWord for passive 24/7 listening.
Near-zero CPU. Triggers callback when wake word detected.
Falls back to keyboard input if model files missing.
"""

import logging
import os
import subprocess
import sys
import threading
import site
import time
from pathlib import Path
from typing import Callable

try:
    from config.settings import SAM_DATA_DIR
    _pkgs = SAM_DATA_DIR / "python-packages"
    if _pkgs.exists() and sys.version_info >= (3, 10):
        site.addsitedir(str(_pkgs))
except Exception:
    pass

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger("SAM.WakeWord")


class WakeWordListener:
    def __init__(self, settings, callback: Callable):
        self.settings = settings
        self.callback = callback
        self._running = False
        self._paused = False
        self._thread = None
        self._model = None
        self._use_keyboard = False
        self._stream = None

    def pause(self):
        """Temporarily pause wake word listening (e.g. during STT recording or TTS playback)."""
        self._paused = True
        logger.debug("WakeWordListener paused")

    def resume(self):
        """Resume wake word listening."""
        self._paused = False
        logger.debug("WakeWordListener resumed")

    @staticmethod
    def play_earcon():
        """Plays an immediate crisp system sound (earcon) when wake word is detected."""
        if sys.platform == "darwin":
            for sound in ["/System/Library/Sounds/Ping.aiff", "/System/Library/Sounds/Tink.aiff", "/System/Library/Sounds/Pop.aiff"]:
                if os.path.exists(sound):
                    try:
                        subprocess.Popen(["/usr/bin/afplay", sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                    except Exception:
                        pass
        # Terminal bell fallback
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass

    @staticmethod
    def notify_api_wake_event():
        """Optionally broadcast wake event to SAM desktop app via local API server."""
        def _notify():
            try:
                import urllib.request
                import json
                req = urllib.request.Request(
                    "http://127.0.0.1:8420/api/voice/wake-event",
                    data=json.dumps({"detected": True, "timestamp": time.time()}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=1.0) as resp:
                    pass
            except Exception:
                pass
        threading.Thread(target=_notify, daemon=True).start()

    def _load_model(self):
        """Load openWakeWord model with proper error handling."""
        if np is None:
            logger.warning("numpy not installed — using keyboard fallback for wake word")
            self._model = None
            self._use_keyboard = True
            return

        try:
            # Download default models if missing
            import openwakeword
            openwakeword.utils.download_models()

            from openwakeword.model import Model
            # hey_jarvis + alexa covers "hey sam", "sam", and "jarvis" acoustic features
            self._model = Model(
                wakeword_models=["hey_jarvis", "alexa"],
                inference_framework="onnx"
            )
            logger.info("openWakeWord models loaded (hey_jarvis, alexa)")

        except Exception as e:
            logger.warning(f"openWakeWord failed ({e}) — using keyboard fallback")
            self._model = None
            self._use_keyboard = True

    def _listen_loop(self):
        """Main listening loop with exclusive microphone management and earcon feedback."""
        if self._use_keyboard or self._model is None:
            logger.info("Keyboard fallback mode active")
            self._keyboard_fallback()
            return

        retry_count = 0
        while self._running:
            try:
                import pyaudio
                CHUNK = 1280
                FORMAT = pyaudio.paInt16
                CHANNELS = 1
                RATE = 16000

                audio = pyaudio.PyAudio()
                stream = audio.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK
                )
                self._stream = stream

                logger.info(f"Listening for wake word: '{self.settings.wake_word}'")
                retry_count = 0

                while self._running:
                    if self._paused:
                        time.sleep(0.1)
                        continue

                    try:
                        raw_data = stream.read(CHUNK, exception_on_overflow=False)
                    except Exception as stream_err:
                        if self._paused:
                            time.sleep(0.1)
                            continue
                        raise stream_err

                    if not raw_data:
                        continue
                    audio_chunk = np.frombuffer(raw_data, dtype=np.int16)
                    prediction = self._model.predict(audio_chunk)

                    threshold = getattr(self.settings, "wake_word_threshold", 0.5)
                    effective_threshold = min(threshold, 0.22)

                    detected = False
                    for model_name, score in prediction.items():
                        if score >= effective_threshold:
                            logger.info(f"Wake word detected via {model_name} (score: {score:.2f})")
                            detected = True
                            break

                    if detected:
                        # 1. Audible earcon confirmation so user knows SAM heard them
                        self.play_earcon()

                        # 2. Inform local API server / desktop UI
                        self.notify_api_wake_event()

                        # 3. Stop stream and pause wake word to release microphone for STT
                        self._paused = True
                        try:
                            stream.stop_stream()
                        except Exception:
                            pass

                        # 4. Invoke the STT callback with dedicated microphone access
                        try:
                            self.callback()
                        except Exception as cb_err:
                            logger.error(f"Wake word callback failed: {cb_err}", exc_info=True)

                        # 5. Cooldown and prediction state flush
                        try:
                            if hasattr(self._model, "reset"):
                                self._model.reset()
                        except Exception:
                            pass

                        time.sleep(1.0) # brief acoustic cooldown

                        # 6. Reopen/restart stream for next wake word
                        try:
                            if self._running:
                                stream.start_stream()
                        except Exception:
                            pass
                        self._paused = False

                try:
                    stream.stop_stream()
                    stream.close()
                except Exception:
                    pass
                audio.terminate()
                self._stream = None
                break

            except Exception as e:
                logger.warning(f"Wake word audio stream encountered error: {e}")
                retry_count += 1
                if retry_count > 5:
                    logger.error("Audio device repeatedly failed — switching to keyboard fallback")
                    self._keyboard_fallback()
                    break
                time.sleep(2)

    def _keyboard_fallback(self):
        """
        Press ENTER to trigger SAM.
        This is the active mode until openWakeWord models are confirmed working.
        """
        if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            logger.info("Non-interactive daemon environment detected; keyboard fallback waiting passively.")
            while self._running:
                time.sleep(1)
            return

        print("\n" + "="*50)
        print("SAM KEYBOARD MODE")
        print("Press ENTER to speak to SAM")
        print("Type 'quit' to exit")
        print("="*50 + "\n")

        while self._running:
            try:
                user_input = input(">> Press ENTER to activate SAM: ")
                if user_input.lower().strip() == "quit":
                    self._running = False
                    break
                self.play_earcon()
                self.notify_api_wake_event()
                self.callback()
            except (EOFError, KeyboardInterrupt):
                break

    def start(self):
        """Start listening. Blocks until stop() is called."""
        self._running = True
        self._paused = False
        self._load_model()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        self._thread.join()

    def stop(self):
        self._running = False
        self._paused = True
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Wake word listener stopped")
