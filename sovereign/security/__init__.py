"""
SIH26117 — document trust boundary. See document_trust.py: extracted
document content is data to analyze, never an instruction to follow.
"""

from .document_trust import UNTRUSTED_DOCUMENT_INSTRUCTION, wrap_untrusted

__all__ = ["UNTRUSTED_DOCUMENT_INSTRUCTION", "wrap_untrusted"]
