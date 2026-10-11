"""Cross-surface diagnostic redaction contract for configured provider endpoints."""

from __future__ import annotations

import pytest

from deeper_dive.diagnostics import (
    DiagnosticEvent,
    StructuredDiagnosticLog,
    export_diagnostic_bundle,
    redact,
    sanitize_exception_message,
)
from deeper_dive.user_config import ProviderConfig


@pytest.mark.parametrize(
    "query",
    [
        "api%252Ekey=matrix-canary",
        "session.Token=matrix-canary",
        "safe=1&%252561pi_key=matrix-canary",
    ],
)
def test_encoded_query_secret_never_crosses_diagnostic_surfaces(tmp_path, query: str) -> None:
    endpoint = f"https://example.test/v1?{query}"
    with pytest.raises(ValueError, match="credential query") as error:
        ProviderConfig(provider_type="openai", base_url=endpoint)
    assert "matrix-canary" not in str(error.value)

    safe = str(redact(f"request={endpoint} status=401"))
    assert "matrix-canary" not in safe
    assert "status=401" in safe

    try:
        try:
            raise ValueError(f"failed {endpoint}")
        except ValueError as cause:
            raise RuntimeError("provider request failed") from cause
    except RuntimeError as error:
        exception_text = sanitize_exception_message(error)
    assert "matrix-canary" not in exception_text
    assert "provider request failed" in exception_text

    log_path = tmp_path / "events.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(
            level="error",
            event="provider_failure",
            details={"nested": [{"endpoint": endpoint}]},
        )
    )
    bundle_path = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics={"nested": [{"endpoint": endpoint}]},
    )
    assert "matrix-canary" not in log_path.read_text(encoding="utf-8")
    assert "matrix-canary" not in bundle_path.read_text(encoding="utf-8")
    assert "[REDACTED]" in bundle_path.read_text(encoding="utf-8")
