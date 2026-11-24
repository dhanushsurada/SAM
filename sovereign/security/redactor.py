"""
SAM Privacy Redactor — Automatic sensitive data scrubbing.

Detects and redacts credentials, API keys, passwords, bearer tokens,
and private keys from logs, memory context, and task results.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Union

# Common credential patterns
_PATTERNS = [
    # OpenAI, Anthropic, OpenRouter, Groq, HuggingFace, GitHub tokens
    (re.compile(r"(sk-[a-zA-Z0-9]{20,})", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"(ghp_[a-zA-Z0-9]{36,})", re.IGNORECASE), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"(gsk_[a-zA-Z0-9]{20,})", re.IGNORECASE), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"(Bearer\s+)[a-zA-Z0-9_\-\.]{20,}", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    # JWT tokens
    (re.compile(r"eyJ[a-zA-Z0-9_\-]{10,}\.eyJ[a-zA-Z0-9_\-]{10,}\.[a-zA-Z0-9_\-]{10,}"), "[REDACTED_JWT]"),
    # Private Key blocks
    (re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]+?-----END [A-Z ]+ PRIVATE KEY-----"), "[REDACTED_PRIVATE_KEY]"),
    # Password query parameters or JSON fields
    (re.compile(r'("password"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'("secret"\s*:\s*")[^"]+(")', re.IGNORECASE), r'\1[REDACTED]\2'),
    (re.compile(r'(password=)[^\s&]+', re.IGNORECASE), r'\1[REDACTED]'),
]


class PrivacyRedactor:
    """Scrubs sensitive credentials and tokens from text or dict structures."""

    @classmethod
    def redact_text(cls, text: str) -> str:
        if not text or not isinstance(text, str):
            return text
        result = text
        for pattern, replacement in _PATTERNS:
            result = pattern.sub(replacement, result)
        return result

    @classmethod
    def redact_structure(cls, data: Any) -> Any:
        if isinstance(data, str):
            return cls.redact_text(data)
        elif isinstance(data, dict):
            return {k: cls.redact_structure(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.redact_structure(item) for item in data]
        return data
