"""End-to-end diagnostic output regression matrix for secret-bearing provider failures."""

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
from deeper_dive.secrets import redact_data

_SECRET_CANARIES = (
    "basic-secret-canary",
    "token-secret-canary",
    "url-user-canary",
    "url-key-canary",
    "inner-secret-canary",
)


def _assert_no_canaries(value: str) -> None:
    for canary in _SECRET_CANARIES:
        assert canary not in value
    assert "[REDACTED]" in value


def test_nested_diagnostics_logs_and_export_bundle_are_sanitized(tmp_path: Path) -> None:
    nested = {
        "messages": (
            "Authorization: Basic basic-secret-canary; status=401",
            {"detail": "authorization=Token token-secret-canary"},
            [
                "https://url-user-canary@api.example.test/v1?key=url-key-canary",
                "status=401; retry_after=30",
            ],
        ),
        "authorization": "Token token-secret-canary",
        "provider": "ollama",
    }
    safe = redact(nested)
    _assert_no_canaries(json.dumps(safe))
    _assert_no_canaries(json.dumps(redact_data(nested)))

    log_path = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(
            level="error",
            event="provider_error",
            message="Authorization: Basic basic-secret-canary",
            details=nested,
        )
    )
    logged = log_path.read_text(encoding="utf-8")
    _assert_no_canaries(logged)
    assert json.loads(logged)["event"] == "provider_error"

    destination = tmp_path / "diagnostic-bundle.json"
    export_diagnostic_bundle(
        destination,
        provider_diagnostics=nested,
        configuration={"provider": "ollama", "authorization": "Token token-secret-canary"},
        source_excerpts={"example": "Authorization: Basic basic-secret-canary"},
        include_source_excerpts=True,
    )
    serialized = destination.read_text(encoding="utf-8")
    _assert_no_canaries(serialized)
    assert json.loads(serialized)["source_excerpts_included"] is True
    assert "ollama" in serialized


def test_provider_error_sanitizes_entire_causal_chain() -> None:
    inner = RuntimeError("Authorization: Basic inner-secret-canary")
    outer = OSError("https://url-user-canary@api.example.test/v1?key=url-key-canary")
    outer.__cause__ = inner
    error = sanitize_provider_error("ollama", outer)
    _assert_no_canaries(json.dumps(error.payload()))
    assert error.event == "provider_error"


def test_sanitizer_preserves_benign_prose_and_urls() -> None:
    original = (
        "tokenization succeeded; model=qwen3.5; status=200; "
        "url=https://example.test/v1?model=qwen3.5&limit=3"
    )
    assert redact(original) == original
