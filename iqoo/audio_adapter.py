"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to multimodal/audio/adapter.py (transcribing
arbitrary audio bytes, reusing ears/stt.py's loaded Whisper model, is a
generic SAM perception capability, not iQOO-specific). This module
re-exports the same class so `import iqoo.audio_adapter` keeps working for
anything outside this repo that still references the old path. There is no
separate implementation here.

New code should import from multimodal.audio (or multimodal.audio.adapter)
directly.
"""
from multimodal.audio.adapter import AudioAdapter  # noqa: F401

__all__ = ["AudioAdapter"]
