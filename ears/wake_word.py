"""
THE EARS — Part 1: Wake Word Detection
Uses openWakeWord for passive 24/7 listening.
Near-zero CPU. Triggers callback when wake word detected.
Falls back to keyboard input if model files missing.
"""

import logging
import threading
import site
from pathlib import Path
from typing import Callable

try:
    from config.settings import SAM_DATA_DIR
    _pkgs = SAM_DATA_DIR / "python-packages"
    if _pkgs.exists():
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
        self._thread = None
        self._model = None
        self._use_keyboard = False

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
            # hey_jarvis + alexa covers "hey sam" and "sam" acoustic features
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
        """Main listening loop with auto-recovery."""
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

                logger.info(f"Listening for wake word: '{self.settings.wake_word}'")
                retry_count = 0

                while self._running:
                    raw_data = stream.read(CHUNK, exception_on_overflow=False)
                    if not raw_data:
                        continue
                    audio_chunk = np.frombuffer(raw_data, dtype=np.int16)
                    prediction = self._model.predict(audio_chunk)

                    threshold = getattr(self.settings, "wake_word_threshold", 0.5)
                    # Adaptive threshold for proxy phonetic activation of "hey sam" / "sam"
                    effective_threshold = min(threshold, 0.22)

                    for model_name, score in prediction.items():
                        if score >= effective_threshold:
                            logger.info(f"Wake word detected via {model_name} (score: {score:.2f})")
                            threading.Thread(
                                target=self.callback,
                                daemon=True
                            ).start()
                            import time
                            time.sleep(2)
                            break

                stream.stop_stream()
                stream.close()
                audio.terminate()
                break

            except Exception as e:
                logger.warning(f"Wake word audio stream encountered error: {e}")
                retry_count += 1
                if retry_count > 5:
                    logger.error("Audio device repeatedly failed — switching to keyboard fallback")
                    self._keyboard_fallback()
                    break
                import time
                time.sleep(2)

    def _keyboard_fallback(self):
        """
        Press ENTER to trigger SAM.
        This is the active mode until openWakeWord models are confirmed working.
        """
        import sys
        if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            logger.info("Non-interactive daemon environment detected; keyboard fallback waiting passively.")
            while self._running:
                import time
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
                threading.Thread(target=self.callback, daemon=True).start()
            except (EOFError, KeyboardInterrupt):
                break

    def start(self):
        """Start listening. Blocks until stop() is called."""
        self._running = True
        self._load_model()
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        self._thread.join()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("Wake word listener stopped")
