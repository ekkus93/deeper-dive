"""5PR-08: sanitizer gaps that predate the fifth cycle, with benign counterparts."""

from __future__ import annotations

import time

import pytest

from deeper_dive.diagnostics import MAX_REDACTED_TEXT_CHARS, redact

C = "CANARY9x"

LEAKS = {
    "apikey assignment": f"apikey={C}",
    "accesstoken assignment": f"accesstoken={C}",
    "clientsecret assignment": f"clientsecret={C}",
    "passwd assignment": f"passwd={C}",
    "csrftoken assignment": f"csrftoken={C}",
    "apikey json": f'{{"apikey": "{C}"}}',
    "passwd mapping": f"{{'passwd': '{C}'}}",
    "clientsecret json": f'{{"clientsecret": "{C}"}}',
    "accesstoken compact json": f'{{"accesstoken":"{C}"}}',
    "pem after key name": (
        f"private_key: -----BEGIN PRIVATE KEY-----\nMIIE{C}abc\n-----END PRIVATE KEY-----"
    ),
    "pem bare": f"-----BEGIN RSA PRIVATE KEY-----\nMIIE{C}abc\n-----END RSA PRIVATE KEY-----",
    "pem encrypted unterminated": f"-----BEGIN ENCRYPTED PRIVATE KEY-----\nMIIE{C}abc",
    "bytes authorization header": f"{{b'Authorization': b'Bearer {C}'}}",
    "bytes header tuple": f"[(b'authorization', b'Bearer {C}')]",
    "unclosed double-quoted api key": f'{{"api_key": "{C}',
    "unclosed single-quoted password": f"{{'password': '{C}",
    "percent-encoded postgres url": f"postgres%3A%2F%2Fuser%3A{C}%40db",
    "double-encoded custom url": f"myapp%253A%252F%252Fuser%253A{C}%2540host",
    "custom scheme fragment after state": f"myapp://cb#state=1,code={C}",
    # The cap cuts inside the secret: the canary starts before the cut, no "@" survives.
    "url password cut by the cap": f"https://user:{C}" + "x" * MAX_REDACTED_TEXT_CHARS + "@host/x",
    "authorization value cut by the cap": f'"authorization": "{C}' + "x" * MAX_REDACTED_TEXT_CHARS,
}


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_no_canary_survives(name: str) -> None:
    assert C not in str(redact(LEAKS[name])), name
    assert C not in str(redact({"detail": [LEAKS[name]]})), name


BENIGN = [
    "max_tokens=100 and tokens=5",
    "the tokenizer uses 3 tokens per word",
    "-----BEGIN CERTIFICATE-----\nMIIBxyz\n-----END CERTIFICATE-----",
    "-----BEGIN PUBLIC KEY-----\nMIIBxyz\n-----END PUBLIC KEY-----",
    "the passwd file lives in /etc",
    "https://example.com/docs#state=1,mode=dark",
    "https://example.com/a#x=1, then more text",
    "postgres%3A%2F%2Fdb.example.com%2Fdata",
    '{"key": "value", "name": "x"}',
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_is_unchanged(text: str) -> None:
    assert redact(text) == text


def test_new_passes_stay_linear_at_the_cap() -> None:
    shapes = {
        "unclosed quotes": '{"api_key": "' * (MAX_REDACTED_TEXT_CHARS // 13),
        "pem openers": "-----BEGIN PRIVATE KEY-----" * (MAX_REDACTED_TEXT_CHARS // 27),
        "encoded schemes": "aa%3A%2F%2F" * (MAX_REDACTED_TEXT_CHARS // 11),
        "fragment pairs": "myapp://cb#" + "a=1," * (MAX_REDACTED_TEXT_CHARS // 4),
        "scheme tail": "x://" * (MAX_REDACTED_TEXT_CHARS // 4),
    }
    for name, text in shapes.items():
        start = time.perf_counter()
        redact(text[: MAX_REDACTED_TEXT_CHARS + 100])
        assert time.perf_counter() - start < 4.0, name
