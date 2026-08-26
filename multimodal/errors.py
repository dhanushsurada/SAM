"""
SAM Multimodal — Perception errors.

(Moved here in Phase 3A.5 — this originated as iqoo/errors.py during
Phase 2 of the iQOO hackathon branch, but is generic SAM perception
functionality with no iQOO/vivo dependency. iqoo/errors.py now forwards
here for backward compatibility.)

Distinct from a generic execution failure so the gateway can report
"SAM couldn't understand your photo/voice" differently from "SAM
started but the task itself failed", and so cancellation during
perception is reported as cancelled, not failed.
"""


class PerceptionError(Exception):
    """Vision or audio interpretation failed. Never silently swallowed —
    always surfaces to the task's error field and an SSE 'failed' event."""


class PerceptionCancelled(Exception):
    """Cancellation was requested while perception (vision/audio
    interpretation) was in progress, before the Brain/Planner/ReAct
    pipeline was ever reached."""
