"""
iQOO Phase 2 — Audio Adapter.

Transcribes an uploaded phone recording using SAM's existing Whisper
infrastructure (ears/stt.py::SpeechToText). Does NOT create a second
speech system.

Design note / known coupling (flagged honestly, see PROGRESS.md and the
Phase 2 completion report): ears/stt.py's public method, `listen()`,
records from a LOCAL microphone via pyaudio and transcribes what it
just recorded — it has no entry point for "transcribe this file I
already have," because it was never asked to have one until now. Rather
than modify ears/stt.py (a file outside iqoo/, which the Phase 2
instructions require stopping to justify before touching), this adapter
reuses SpeechToText's model-loading method (`_load_model()`, which
carries the real value: faster-whisper import handling, Apple Silicon
device detection, lazy-load caching, and the speech_recognition
fallback flag) and its loaded model object directly, feeding it an
uploaded file instead of a live recording.

This is a deliberate, documented trade-off: it reaches into two
underscore-prefixed attributes of another module's class instead of a
clean public method. The correct long-term fix — adding a
`transcribe_file(path)` public method to SpeechToText itself — is a
three-line additive change to ears/stt.py that was NOT made in this
phase, specifically to honor the instruction to stop and explain before
touching any file outside iqoo/, client/, tests/, docs/iqoo/. It's
recommended as a fast-follow (see PROGRESS.md "Next Action").
"""

import base64
import logging
import os
import tempfile

from iqoo.errors import PerceptionError
from iqoo.media_validation import AUDIO_MIME_SUFFIX

logger = logging.getLogger("SAM.iQOO.Audio")


class AudioAdapter:
    def __init__(self, settings):
        self.settings = settings
        self._stt = None  # lazy ears.stt.SpeechToText instance, for model reuse only

    def _get_stt(self):
        if self._stt is None:
            from ears.stt import SpeechToText  # existing SAM STT, not duplicated
            self._stt = SpeechToText(self.settings)
            self._stt._load_model()  # reuse existing lazy-load/device-detection/fallback logic verbatim
        return self._stt

    def transcribe(self, attachment: dict) -> str:
        """attachment: {"kind": "audio", "mime_type": ..., "data": <base64>}.
        Returns the transcript. Raises PerceptionError on any failure —
        including a genuinely silent/empty recording, so a task never
        silently proceeds with a missing instruction."""
        stt = self._get_stt()

        try:
            audio_bytes = base64.b64decode(attachment["data"], validate=True)
        except Exception as e:
            raise PerceptionError(f"Could not decode audio attachment: {e}") from e

        suffix = AUDIO_MIME_SUFFIX.get(attachment.get("mime_type", ""), ".bin")
        tmp_path = tempfile.mktemp(suffix=suffix)

        try:
            with open(tmp_path, "wb") as f:
                f.write(audio_bytes)

            if stt._model is not None:
                return self._transcribe_with_whisper(stt, tmp_path)
            return self._transcribe_with_fallback(tmp_path, suffix)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def _transcribe_with_whisper(self, stt, tmp_path: str) -> str:
        try:
            # Same call shape as ears/stt.py::listen() — faster-whisper
            # decodes most container formats (webm/mp4/ogg/wav) itself via
            # PyAV, so no manual audio conversion is needed here.
            segments, info = stt._model.transcribe(
                tmp_path, language="en", beam_size=5, vad_filter=True
            )
            transcript = " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            raise PerceptionError(f"Whisper transcription failed: {e}") from e

        if not transcript:
            raise PerceptionError(
                "Transcription produced no text — the recording may be silent or too short")
        logger.info(f"Transcribed: '{transcript}'")
        return transcript

    def _transcribe_with_fallback(self, tmp_path: str, suffix: str) -> str:
        # ears/stt.py's own fallback (speech_recognition + Google) only
        # accepts WAV/AIFF/FLAC via sr.AudioFile — honestly refuse rather
        # than silently mis-transcribing or crashing on webm/ogg/mp4,
        # which is what a phone browser's MediaRecorder actually produces
        # most often.
        if suffix not in (".wav", ".aiff", ".flac"):
            raise PerceptionError(
                f"No faster-whisper installed, and the fallback speech recognizer only "
                f"supports WAV/AIFF/FLAC audio (got {suffix}). Install faster-whisper "
                f"for full format support."
            )
        try:
            import speech_recognition as sr
            recognizer = sr.Recognizer()
            with sr.AudioFile(tmp_path) as source:
                audio = recognizer.record(source)
            transcript = recognizer.recognize_google(audio)
        except Exception as e:
            raise PerceptionError(f"Fallback speech recognition failed: {e}") from e

        if not transcript.strip():
            raise PerceptionError("Fallback transcription produced no text")
        return transcript
