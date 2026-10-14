"""TPR-19.4 / 19.5: fragment redaction keeps context; wider credential coverage."""

from __future__ import annotations

import pytest

from deeper_dive.diagnostics import redact

_CANARY = "CANARY-SECRET-123"


def _text(value: str) -> str:
    result = redact(value)
    assert isinstance(result, str)
    return result


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '{"url":"https://h/x#access_token=CANARY-SECRET-123","k":1}',
            '{"url":"https://h/x#[REDACTED]","k":1}',
        ),
        (
            "see https://h/x#access_token=CANARY-SECRET-123 now",
            "see https://h/x#[REDACTED] now",
        ),
        (
            "[link](https://h/x#access_token=CANARY-SECRET-123) after",
            "[link](https://h/x#[REDACTED]) after",
        ),
        (
            "a https://h/x#token=CANARY-SECRET-123 b https://h/y#id_token=CANARY-SECRET-123 c",
            "a https://h/x#[REDACTED] b https://h/y#[REDACTED] c",
        ),
    ],
)
def test_fragment_redaction_preserves_surrounding_context(raw: str, expected: str) -> None:
    assert _text(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "wss://user:CANARY-SECRET-123@h/x",
        "ftp://user:CANARY-SECRET-123@h/file",
        "https://h/x?code=CANARY-SECRET-123",
        "https://h/x?a=1&sig=CANARY-SECRET-123",
        "https://h/x?a=1&X-Amz-Signature=CANARY-SECRET-123&b=2",
        "https://h/x?X-Goog-Signature=CANARY-SECRET-123",
        "https://h/x#state=1&code=CANARY-SECRET-123",
        "https://h/x?id_token=CANARY-SECRET-123&refresh_token=CANARY-SECRET-123",
        "https://h/x%23access_token%3DCANARY-SECRET-123",
        "https://h/x%2523access_token%253DCANARY-SECRET-123",
    ],
)
def test_credential_bearing_urls_are_redacted(raw: str) -> None:
    assert _CANARY not in _text(raw)


@pytest.mark.parametrize(
    "raw",
    [
        "https://h/docs#section-2, thanks",
        "https://h/path?page=2&sort=asc",
        "see https://example.com/a%20b for details",
        "status code 200 from https://h/x",
        "wss://h/socket",
    ],
)
def test_benign_urls_are_unchanged(raw: str) -> None:
    assert _text(raw) == raw
