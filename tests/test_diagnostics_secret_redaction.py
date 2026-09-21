import pytest

from deeper_dive.diagnostics import redact, sanitize_provider_error


@pytest.mark.parametrize(
    ("text", "sensitive_value"),
    [
        ("Authorization: " + "Bearer " + "VALUE.ONE", "VALUE.ONE"),
        ("api" + "_key" + "=" + "VALUE_TWO", "VALUE_TWO"),
        ("to" + "ken" + ":" + "VALUE_THREE", "VALUE_THREE"),
        ("PASS" + "WORD" + "=" + "VALUE_FOUR", "VALUE_FOUR"),
        ("request https://alice:" + "VALUE_FIVE" + "@example.test/v1 failed", "VALUE_FIVE"),
    ],
)
def test_redact_removes_common_inline_secret_forms(text: str, sensitive_value: str) -> None:
    sanitized = str(redact(text))
    assert sensitive_value not in sanitized
    assert "[REDACTED]" in sanitized


def test_redact_preserves_non_secret_context() -> None:
    text = "provider=openai status=401 " + "api" + "_key" + "=" + "VALUE_SIX request failed"
    sanitized = str(redact(text))
    assert "provider=openai" in sanitized
    assert "status=401" in sanitized
    assert "request failed" in sanitized
    assert "VALUE_SIX" not in sanitized


def test_provider_error_uses_canonical_redaction() -> None:
    message = (
        "401 from https://user:"
        + "VALUE_SEVEN"
        + "@example.test "
        + "api"
        + "_key"
        + "="
        + "VALUE_EIGHT"
    )
    event = sanitize_provider_error("openai", RuntimeError(message))
    assert "VALUE_SEVEN" not in event.message
    assert "VALUE_EIGHT" not in event.message
    assert "401" in event.message
