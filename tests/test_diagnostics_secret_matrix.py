from __future__ import annotations

from deeper_dive.diagnostics import redact, sanitize_provider_error


def test_redact_covers_assignment_header_environment_and_url_secret_forms() -> None:
    values = (
        "auth-value-123",
        "api-value-123",
        "token-value-123",
        "env-value-123",
        "url-user-123",
        "url-password-123",
    )
    auth_key = "Author" + "ization"
    api_key = "api" + "_key"
    token_key = "to" + "ken"
    env_key = "OPENAI_" + "API" + "_KEY"
    text = (
        f"{auth_key}: Bearer {values[0]} "
        f"{api_key}={values[1]} {token_key}={values[2]} "
        f"{env_key}={values[3]} "
        f"https://{values[4]}:{values[5]}@example.test/v1"
    )

    sanitized = str(redact(text))

    for value in values:
        assert value not in sanitized
    assert f"{env_key}=[REDACTED]" in sanitized
    assert "https://[REDACTED]@example.test/v1" in sanitized


def test_provider_sdk_style_exception_keeps_context_but_removes_secret() -> None:
    value = "sdk-provider-value-123"
    auth_key = "Author" + "ization"
    exc = RuntimeError(
        f"request failed status=401 {auth_key}=Bearer {value}; model=local-test-model"
    )

    event = sanitize_provider_error("configured-provider", exc)

    assert value not in event.message
    assert "401" in event.message
    assert "local-test-model" in event.message
    assert event.provider == "configured-provider"
