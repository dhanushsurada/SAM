"""
Compatibility forwarding layer — Phase 3A.5 architecture migration.

The real implementation moved to multimodal/vision/adapter.py (interpreting
an arbitrary photo via a vision model is a generic SAM perception capability,
not iQOO-specific — it doesn't touch anything iQOO/vivo-related). This
module re-exports the same class so `import iqoo.vision_adapter` keeps
working for anything outside this repo that still references the old path.
There is no separate implementation here.

New code should import from multimodal.vision (or multimodal.vision.adapter)
directly.
"""
from multimodal.vision.adapter import VisionAdapter  # noqa: F401

__all__ = ["VisionAdapter"]
