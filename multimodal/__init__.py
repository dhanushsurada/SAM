"""
SAM Multimodal — perception capabilities (vision, audio).

Generic SAM capabilities, not iQOO-specific. Introduced under iqoo/ during
the iQOO hackathon branch's Phase 2, relocated here in Phase 3A.5 once the
long-term architecture was finalized. See docs/iqoo/PHASE_3A5_MIGRATION.md.

Note: hands/vision/screen_reader.py (reads the LOCAL machine's screen for
click-coordinate targeting) and ears/ (wake word + live-microphone STT) are
deliberately NOT part of this package — they are a different capability
(local computer control / the live voice loop) that predates and is
unrelated to the iQOO perception adapters below.
"""
from .errors import PerceptionError, PerceptionCancelled

__all__ = ["PerceptionError", "PerceptionCancelled"]
