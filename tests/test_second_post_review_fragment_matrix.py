"""Cross-surface credential fragment matrix for supported URL encodings."""

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
    "fragment",
    [
        "safe=1;api%5Fkey=fragment-matrix-canary",
        "safe%3D1%26access_token%3Dfragment-matrix-canary",
        "client.secret=fragment-matrix-canary",
        "session%54oken=fragment-matrix-canary",
        "%2561pi_key%3Dfragment-matrix-canary",
    ],
)
def test_fragment_canary_is_rejected_and_redacted_across_surfaces(
tmp_path, fragment: str) -> None:
    endpoint = f"https://example.test/v1#{fragment}"
    with pytest.raises(ValueError, match="fragments") as rejected:
        ProviderConfig(provider_type="openai", base_url=endpoint)
    assert "fragment-matrix-canary" not in str(rejected.value)

    safe = str(redact(f"GET {endpoint} status=401"))
    assert "fragment-matrix-canary" not in safe
    assert "status=401" in safe
    assert "#[REDACTED]" in safe
    assert "fragment-matrix-canary" not in sanitize_exception_message(
        RuntimeError(f"provider failed: {endpoint}")
    )

    log = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(log).emit(
        DiagnosticEvent(level="error", event="provider_error", details={"url": endpoint})
    )
    assert b"fragment-matrix-canary" not in log.read_bytes()
    bundle = export_diagnostic_bundle(
        tmp_path / "diagnostics.json", provider_diagnostics={"url": endpoint}
    )
    assert b"fragment-matrix-canary" not in bundle.read_bytes()
