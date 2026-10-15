"""5PR-08: sanitizer gaps that predate the fifth cycle, with benign counterparts."""

from __future__ import annotations

import pytest
from linear_timing import assert_scales_linearly

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
    # Pre-existing coverage: the older Bearer rule redacts these on the baseline too
    # (the non-Bearer bytes shapes are in test_sixth_post_review_credential_shapes.py).
    "bytes authorization header": f"{{b'Authorization': b'Bearer {C}'}}",
    "bytes header tuple": f"[(b'authorization', b'Bearer {C}')]",
    "unclosed double-quoted api key": f'{{"api_key": "{C}',
    "unclosed single-quoted password": f"{{'password': '{C}",
    "percent-encoded postgres url": f"postgres%3A%2F%2Fuser%3A{C}%40db",
    "double-encoded custom url": f"myapp%253A%252F%252Fuser%253A{C}%2540host",
    "custom scheme fragment after state": f"myapp://cb#state=1,code={C}",
    # The cap cuts inside the secret: the canary starts before the cut, no "@" survives.
    "url password cut by the cap": f"https://user:{C}" + "x" * MAX_REDACTED_TEXT_CHARS + "@host/x",
    # Pre-existing coverage: the unclosed-quote rule predates the cycle.
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
        "unclosed quotes": ('{"api_key": "', 13),
        "pem openers": ("-----BEGIN PRIVATE KEY-----", 27),
        "encoded schemes": ("aa%3A%2F%2F", 11),
        "fragment pairs": ("a=1,", 4),
        "scheme tail": ("x://", 4),
    }
    for name, (unit, _width) in shapes.items():
        prefix = "myapp://cb#" if name == "fragment pairs" else ""

        def make(size: int, unit: str = unit, prefix: str = prefix) -> str:
            return (prefix + unit * (size // len(unit) + 1))[:size]

        assert_scales_linearly(redact, make, large=MAX_REDACTED_TEXT_CHARS, label=name)


REVIEW_LEAKS = {
    "pgp private key block": (
        f"-----BEGIN PGP PRIVATE KEY BLOCK-----\n{C}\n-----END PGP PRIVATE KEY BLOCK-----"
    ),
    "lowercase pem": f"-----begin private key-----\n{C}\n-----end private key-----",
    "plus in encoded scheme": f"redis%2Bssl%3A%2F%2Fu%3A{C}%40h",
    "git plus ssh encoded": f"git%2Bssh%3A%2F%2Fu%3A{C}%40host",
    "dollar host": f"postgres://u:{C}/a@$HOST",
}


@pytest.mark.parametrize("name", sorted(REVIEW_LEAKS))
def test_review_leaks_are_closed(name: str) -> None:
    assert C not in str(redact(REVIEW_LEAKS[name])), name


@pytest.mark.parametrize(
    "text",
    [
        "http://localhost:3000/api/users/@me",
        "https://registry.npmjs.org:443/@types/node",
        "https://medium.com:443/@author/post",
    ],
)
def test_path_segments_starting_with_at_are_not_userinfo(text: str) -> None:
    assert redact(text) == text
