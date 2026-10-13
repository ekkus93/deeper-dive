"""Percent-encoded complete URLs must not bypass diagnostic redaction."""

from __future__ import annotations

import pytest

from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
    sanitize_exception_message,
)


@pytest.mark.parametrize(
    "encoded",
    [
        "https%3A%2F%2Fexample.test%2Fv1%23access_token%3Dencoded-url-canary",
        "https%253A%252F%252Fexample.test%252Fv1%2523access_token%253Dencoded-url-canary",
        "https%3A%2F%2Fexample.test%2Fv1%3Fsession.Token%3Dencoded-url-canary",
        "HTTPS%3A%2F%2Fexample.test%2Fv1%23access_token%3Dencoded-url-canary",
        "HtTpS%253A%252F%252Fexample.test%252Fv1%2523access_token%253Dencoded-url-canary",
    ],
)
def test_complete_encoded_credential_urls_are_redacted_in_all_sinks(tmp_path, encoded: str) -> None:
    message = f"endpoint={encoded} status=401"
    sanitized = str(redact(message))
    assert "encoded-url-canary" not in sanitized
    assert "[REDACTED]" in sanitized
    assert "status=401" in sanitized

    try:
        try:
            raise ValueError(message)
        except ValueError as cause:
            raise RuntimeError("provider failed") from cause
    except RuntimeError as exc:
        exception_text = sanitize_exception_message(exc)
    assert "encoded-url-canary" not in exception_text
    assert "provider failed" in exception_text

    log_path = tmp_path / "events.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(level="error", event="provider_failure", details={"url": encoded})
    )
    bundle_path = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics={"nested": [{"url": encoded}]},
    )
    for path in (log_path, bundle_path):
        contents = path.read_text(encoding="utf-8")
        assert "encoded-url-canary" not in contents
        assert "[REDACTED]" in contents


def test_benign_encoded_url_is_preserved() -> None:
    url = "https%3A%2F%2Fexample.test%2Fdocs%23installation"
    assert redact(url) == url
