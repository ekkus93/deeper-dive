from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_source_excerpts_require_explicit_opt_in_and_provider_errors_are_sanitized(
    tmp_path: Path,
) -> None:
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
            "nested": [
                f"SERVICE_{token_name.upper()}={secret}",
                f"{auth_scheme}: Bearer {secret}",
            ],
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


def test_debug_and_repr_payloads_do_not_leak_original_secret_values() -> None:
    secret = "debug-runtime-value-901"
    key_name = "api" + "_" + "key"
    token_name = "to" + "ken"
    payload = redact(
        {
            "debug": f"ProviderDebug({key_name}={secret!r})",
            "repr": {"raw": f"TokenObject({token_name}={secret})"},
            "safe": "keep useful context",
        }
    )
    text = json.dumps(payload, sort_keys=True)

    assert secret not in text
    assert "ProviderDebug" in text
    assert "TokenObject" in text
    assert f"{key_name}=[REDACTED]" in text
    assert f"{token_name}=[REDACTED]" in text
    assert "keep useful context" in text


@pytest.mark.parametrize("layer_count", (1, 2))
@pytest.mark.parametrize(
    "inner_url",
    (
        "https://username:nested-secret-canary@inner.example/v1",
        "https://inner.example/v1#access_token=nested-secret-canary",
        "https://inner.example/v1#%61ccess_token%3Dnested-secret-canary",
    ),
)
def test_diagnostic_encoded_redirect_hides_nested_userinfo_and_fragments(
    tmp_path: Path, layer_count: int, inner_url: str
) -> None:
    from urllib.parse import quote

    destination = inner_url
    for _ in range(layer_count):
        destination = quote(destination, safe="")
    url = f"https://gateway.example/v1?redirect={destination}&status=ok"
    safe = str(redact(f"request={url} response=401"))
    assert "nested-secret-canary" not in safe
    assert "redirect=[REDACTED]" in safe
    assert "status=ok" in safe
    assert "response=401" in safe

    bundle = export_diagnostic_bundle(
        tmp_path / "nested-redirect.json",
        provider_diagnostics={"requests": [{"url": url}]},
    ).read_text(encoding="utf-8")
    assert "nested-secret-canary" not in bundle
    assert "[REDACTED]" in bundle


@pytest.mark.parametrize("layer_count", (1, 2))
def test_diagnostic_encoded_redirect_retains_benign_fragment(layer_count: int) -> None:
    from urllib.parse import quote

    destination = "https://inner.example/docs#install"
    for _ in range(layer_count):
        destination = quote(destination, safe="")
    url = f"https://gateway.example/docs?redirect={destination}&status=ok"
    assert redact(url) == url


def test_untrusted_diagnostic_mapping_keys_are_redacted_across_exports(
    tmp_path: Path,
) -> None:
    canary = "mapping-key-canary-2026"
    unsafe_key = f"https://example.test/v1#access_token={canary}"
    nested = {"requests": [{unsafe_key: {"status": "failed"}}], "safe": "context"}
    sanitized = json.dumps(redact(nested), sort_keys=True)
    assert canary not in sanitized
    assert "https://example.test/v1#[REDACTED]" in sanitized
    assert '"safe": "context"' in sanitized

    log_path = tmp_path / "events.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(level="error", event="provider_error", details=nested)
    )
    assert canary not in log_path.read_text(encoding="utf-8")

    bundle_path = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        provider_diagnostics=nested,
        configuration={"providers": {unsafe_key: {"type": "fake"}}},
    )
    bundle = bundle_path.read_text(encoding="utf-8")
    assert canary not in bundle
    assert "[REDACTED]" in bundle
    assert '"safe": "context"' in bundle


def test_benign_diagnostic_mapping_keys_keep_identity() -> None:
    payload = {"provider-id": {"https://example.test/docs#overview": "ok"}}
    assert redact(payload) == payload


@pytest.mark.parametrize(
    "credential_key",
    ("session.Token", "api[key]", "api+key", "client/secret"),
)
def test_stringified_punctuated_credential_keys_are_redacted_across_surfaces(
    tmp_path: Path, credential_key: str
) -> None:
    """Untrusted repr/JSON fragments receive the same secret-key treatment as maps."""
    canary = "stringified-key-canary-2026"
    message = (
        f"ProviderError(headers={{'{credential_key}': '{canary}', "
        "'phase': 'retry'}})"
    )
    expected = f"'{credential_key}': '[REDACTED]'"
    sanitized = str(redact(message))
    assert canary not in sanitized
    assert expected in sanitized
    assert "'phase': 'retry'" in sanitized
    assert expected in sanitize_provider_error("fake", RuntimeError(message)).message

    log_path = tmp_path / "quoted-key.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(level="error", event="provider_error", message=message)
    )
    bundle_path = export_diagnostic_bundle(
        tmp_path / "quoted-key.json",
        provider_diagnostics={"sdk_repr": message},
    )
    for output in (log_path.read_text(), bundle_path.read_text()):
        assert canary not in output
        assert "[REDACTED]" in output


def test_benign_quoted_diagnostic_keys_are_preserved() -> None:
    benign = """ProviderError(context={'request.id': 'request-123', 'phase': 'retry'})"""
    assert redact(benign) == benign
