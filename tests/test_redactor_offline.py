"""Tests for PrivacyRedactor sensitive data scrubbing."""

from sovereign.security.redactor import PrivacyRedactor


def test_redact_api_keys():
    text = "Authorization token is sk-1234567890abcdef1234567890 and groq is gsk_1234567890abcdef1234567890"
    scrubbed = PrivacyRedactor.redact_text(text)
    assert "sk-" not in scrubbed
    assert "gsk_" not in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed
    assert "[REDACTED_GROQ_KEY]" in scrubbed


def test_redact_jwt_and_bearer():
    text = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    scrubbed = PrivacyRedactor.redact_text(text)
    assert "Bearer" in scrubbed
    assert "eyJ" not in scrubbed
    assert "[REDACTED" in scrubbed


def test_redact_dict():
    data = {
        "user": "test",
        "api_key": "sk-1234567890abcdef1234567890",
        "nested": {"secret": "super_secret_val"},
    }
    scrubbed = PrivacyRedactor.redact_structure(data)
    assert "sk-" not in scrubbed["api_key"]
    assert "[REDACTED_API_KEY]" in scrubbed["api_key"]
    assert scrubbed["user"] == "test"
