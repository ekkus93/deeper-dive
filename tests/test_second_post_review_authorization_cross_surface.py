"""Authorization schemes must redact across the same durable diagnostic sinks."""

from __future__ import annotations

import json

import pytest

from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
    sanitize_exception_message,
)


@pytest.mark.parametrize("scheme", ["Basic", "Token", "Digest", "Bearer"])
def test_authorization_scheme_canaries_are_private_across_sinks(tmp_path, scheme: str) -> None:
    canary = "authorization-scheme-canary"
    if scheme == "Digest":
        header = f'Digest username="{canary}", realm="test"'
    else:
        header = f"{scheme} {canary}"
    message = f"Authorization: {header}; status=401 action=retry"

    safe = str(redact(message))
    assert canary not in safe
    assert "Authorization: [REDACTED]" in safe
    assert "status=401" in safe
    assert "action=retry" in safe

    try:
        try:
            raise ValueError(message)
        except ValueError as cause:
            raise RuntimeError("provider request failed") from cause
    except RuntimeError as error:
        exception_text = sanitize_exception_message(error)
    assert canary not in exception_text
    assert "provider request failed" in exception_text

    log_path = tmp_path / "provider.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(
            level="error",
            event="provider_error",
            details={"nested": [{"request": message}]},
        )
    )
    bundle_path = export_diagnostic_bundle(
        tmp_path / "support.json",
        provider_diagnostics={"nested": [{"request": message}]},
    )
    for path in (log_path, bundle_path):
        text = path.read_text(encoding="utf-8")
        assert canary not in text
        assert "[REDACTED]" in text
        assert "status=401" in text
        json.loads(text.splitlines()[0] if path == log_path else text)


@pytest.mark.parametrize("scheme", ["Basic", "Token", "Digest", "Bearer"])
def test_unrelated_benign_diagnostic_text_remains_visible(scheme: str) -> None:
    message = f"provider={scheme.lower()} status=200 request=completed"
    assert redact(message) == message
