from __future__ import annotations

import json

from deeper_dive.diagnostics import redact, sanitize_exception_message
from deeper_dive.export import EpisodeExporter


SECRET_VALUE = "credential-value"


def _bearer() -> str:
    return "Bear" + "er credential-value"


def _credential_url() -> str:
    return "https://" + "user:credential-value@example.test/path"


def test_redact_covers_secret_key_variants_and_nested_collections() -> None:
    payload = {
        "authorization": _bearer(),
        "apiKey": SECRET_VALUE,
        "access_token": SECRET_VALUE,
        "refresh-token": SECRET_VALUE,
        "clientSecret": SECRET_VALUE,
        "password": SECRET_VALUE,
        "cookie": SECRET_VALUE,
        "nested": [
            {"url": _credential_url()},
            {"message": "api_key=credential-value; authorization: credential-value"},
        ],
        "set_values": {"token=credential-value"},
    }

    redacted = redact(payload)
    text = json.dumps(redacted, sort_keys=True)

    for key in (
        "authorization",
        "apiKey",
        "access_token",
        "refresh-token",
        "clientSecret",
        "password",
        "cookie",
    ):
        assert redacted[key] == "[REDACTED]"
    assert "credential-value" not in text
    assert "https://[REDACTED]@example.test/path" in text
    assert "Bearer [REDACTED]" in text


def test_redact_preserves_non_secret_false_positive_keys() -> None:
    payload = {
        "tokenizer": "sentencepiece",
        "model_tokens": 8192,
        "secretary": "role",
        "cookiecutter": "template",
        "passwordless": True,
        "apiary_keynote": "talk",
    }

    assert redact(payload) == payload


def test_exception_sanitizer_redacts_cause_and_context() -> None:
    cause = ValueError("api_key=credential-value")
    exc = RuntimeError("provider failed with " + _bearer())
    exc.__cause__ = cause

    message = sanitize_exception_message(exc)

    assert "credential-value" not in message
    assert "Bearer [REDACTED]" in message
    assert "api_key=[REDACTED]" in message


def test_export_metadata_uses_canonical_sanitizer_and_drops_secret_keys(tmp_path) -> None:
    path = tmp_path / "metadata.json"
    EpisodeExporter.write_metadata(
        path,
        {
            "episode_id": "episode-1",
            "provenance": {"model": "fake-v1"},
            "credentials": {
                "access_token": SECRET_VALUE,
                "refresh_token": SECRET_VALUE,
                "client_secret": SECRET_VALUE,
                "cookie": SECRET_VALUE,
            },
            "provider_message": _bearer(),
            "url": _credential_url(),
        },
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(payload, sort_keys=True)

    assert payload["episode_id"] == "episode-1"
    assert payload["provenance"] == {"model": "fake-v1"}
    assert "credentials" in payload
    assert payload["credentials"] == {}
    assert payload["provider_message"] == "Bearer [REDACTED]"
    assert payload["url"] == "https://[REDACTED]@example.test/path"
    assert "credential-value" not in text
