from __future__ import annotations

SENSITIVE_VALUE = "credential" + "-value"


def _diagnostics_module():
    return __import__("deeper_dive.diagnostics", fromlist=["redact", "sanitize_exception_message"])


def _export_module():
    return __import__("deeper_dive.export", fromlist=["EpisodeExporter"])


def _json_module():
    return __import__("json")


def _bearer() -> str:
    return "Bearer " + SENSITIVE_VALUE


def _credential_url() -> str:
    return "https://" + "user:" + SENSITIVE_VALUE + "@example.test/path"


def test_redact_covers_secret_key_variants_and_nested_collections() -> None:
    diagnostics = _diagnostics_module()
    json = _json_module()
    payload = {
        "authorization": _bearer(),
        "apiKey": SENSITIVE_VALUE,
        "access_token": SENSITIVE_VALUE,
        "refresh-token": SENSITIVE_VALUE,
        "clientSecret": SENSITIVE_VALUE,
        "service_token": SENSITIVE_VALUE,
        "service-secret": SENSITIVE_VALUE,
        "password": SENSITIVE_VALUE,
        "cookie": SENSITIVE_VALUE,
        "nested": [
            {"url": _credential_url()},
            {"message": "api_key=credential-value; authorization: credential-value"},
        ],
        "set_values": {"token=credential-value"},
    }

    redacted = diagnostics.redact(payload)
    text = json.dumps(redacted, sort_keys=True)

    assert SENSITIVE_VALUE not in text
    assert "[REDACTED]" in text
    assert "Bearer [REDACTED]" in text
    assert "https://[REDACTED]@example.test/path" in text
    assert "api_key=[REDACTED]" in text
    assert "authorization: [REDACTED]" in text


def test_redact_preserves_non_secret_false_positive_keys() -> None:
    diagnostics = _diagnostics_module()
    payload = {
        "tokenizer": SENSITIVE_VALUE,
        "model_tokens": SENSITIVE_VALUE,
        "secretary": SENSITIVE_VALUE,
        "public_note": "secret sauce is not a credential",
    }

    redacted = diagnostics.redact(payload)

    assert redacted == payload


def test_sanitize_exception_message_redacts_cause_and_context() -> None:
    diagnostics = _diagnostics_module()
    try:
        try:
            raise ValueError("provider failed with service_token=" + SENSITIVE_VALUE)
        except ValueError as cause:
            raise RuntimeError("outer failure client_secret=" + SENSITIVE_VALUE) from cause
    except RuntimeError as exc:
        message = diagnostics.sanitize_exception_message(exc)

    assert SENSITIVE_VALUE not in message
    assert "[REDACTED]" in message
    assert "caused by:" in message


def test_export_metadata_uses_canonical_sanitizer_and_drops_secret_keys(tmp_path) -> None:
    episode_export = _export_module()
    json = _json_module()
    path = tmp_path / "metadata.json"
    metadata = {
        "access_token": SENSITIVE_VALUE,
        "refresh_token": SENSITIVE_VALUE,
        "client_secret": SENSITIVE_VALUE,
        "cookie": SENSITIVE_VALUE,
        "authorization": _bearer(),
        "connection": _credential_url(),
        "provenance": {
            "provider": "fake",
            "model": "fake-v1",
            "run_id": "run-1",
        },
    }

    episode_export.EpisodeExporter.write_metadata(path, metadata)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(loaded, sort_keys=True)

    assert SENSITIVE_VALUE not in text
    assert "access_token" not in loaded
    assert "refresh_token" not in loaded
    assert "client_secret" not in loaded
    assert "cookie" not in loaded
    assert "authorization" not in loaded
    assert loaded["connection"] == "https://[REDACTED]@example.test/path"
    assert loaded["provenance"] == {"model": "fake-v1", "provider": "fake", "run_id": "run-1"}
