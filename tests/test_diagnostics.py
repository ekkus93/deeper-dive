from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
    sanitize_provider_error,
)


def test_structured_log_and_bundle_redact_secrets_and_preserve_run_ids(tmp_path: Path) -> None:
    secret = "recognizable-secret-123"
    log_path = tmp_path / "diagnostics.jsonl"
    logger = StructuredDiagnosticLog(log_path)
    logger.emit(
        DiagnosticEvent(
            level="info",
            event="provider_request",
            run_id="run-42",
            provider="fake",
            details={"Authorization": f"Bearer {secret}", "nested": {"api_key": secret}},
        )
    )
    text = log_path.read_text()
    assert secret not in text
    assert "run-42" in text
    assert "[REDACTED]" in text

    bundle = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        run_id="run-42",
        configuration={"token": secret, "model": "fake-v1"},
        provider_diagnostics={"message": f"Bearer {secret}"},
        source_excerpts={"source-1": "PRIVATE SOURCE CONTENT"},
    )
    payload = json.loads(bundle.read_text())
    assert secret not in bundle.read_text()
    assert payload["run_id"] == "run-42"
    assert payload["source_excerpts_included"] is False
    assert "source_excerpts" not in payload


def test_source_excerpts_require_explicit_opt_in_and_provider_errors_are_sanitized(tmp_path: Path) -> None:
    secret = "provider-secret-456"
    event = sanitize_provider_error("remote", RuntimeError(f"Bearer {secret}"), run_id="run-9")
    assert secret not in event.message
    assert event.run_id == "run-9"

    path = export_diagnostic_bundle(
        tmp_path / "with-source.json",
        source_excerpts={"source-1": "allowed excerpt"},
        include_source_excerpts=True,
    )
    payload = json.loads(path.read_text())
    assert payload["source_excerpts_included"] is True
    assert payload["source_excerpts"] == {"source-1": "allowed excerpt"}


def test_redact_covers_assignment_forms_and_credential_bearing_urls() -> None:
    secret = "runtime-value-789"
    key_name = "api" + "_" + "key"
    token_name = "to" + "ken"
    auth_scheme = "Author" + "ization"
    payload = redact(
        {
            "message": (
                f"{key_name}={secret}; {token_name}: {secret}; "
                f"download=https://user:{secret}@example.test/private"
            ),
            "nested": [f"SERVICE_{token_name.upper()}={secret}", f"{auth_scheme}: Bearer {secret}"],
        }
    )
    text = json.dumps(payload, sort_keys=True)

    assert secret not in text
    assert f"{key_name}=[REDACTED]" in text
    assert f"{token_name}: [REDACTED]" in text
    assert "https://[REDACTED]@example.test/private" in text
    assert f"{auth_scheme}: [REDACTED]" in text


def test_provider_error_sanitization_covers_sdk_exception_shapes() -> None:
    secret = "sdk-runtime-value-012"
    auth_header = "Author" + "ization"
    key_name = "api" + "_" + "key"
    sdk_message = (
        "ProviderError(status=401, "
        f"headers={{{auth_header!r}: '{secret}'}}, "
        f"request_url='https://user:{secret}@example.test/v1', "
        f"body='{key_name}={secret}')"
    )

    event = sanitize_provider_error("sdk", RuntimeError(sdk_message), run_id="run-sdk")

    assert secret not in event.message
    assert event.run_id == "run-sdk"
    assert auth_header in event.message
    assert "https://[REDACTED]@example.test/v1" in event.message
    assert f"{key_name}=[REDACTED]" in event.message
