"""6PR-06: bytes/tuple header reprs, bare keys, CLI flags, XML tags, spaced and escaped values."""

from __future__ import annotations

import pytest

from deeper_dive.diagnostics import redact, sanitize_exception_message

CANARY = "CANARY9x"

LEAKS = {
    "bytes header mapping": f"{{b'Authorization': b'Basic {CANARY}'}}",
    "bytes api key mapping": f"{{b'x-api-key': b'{CANARY}'}}",
    "str key bytes value": f"{{'api_key': b'{CANARY}'}}",
    "bytes tuple list": f"[(b'authorization', b'Basic {CANARY}')]",
    "str tuple list api key": f"[('x-api-key', '{CANARY}')]",
    "str tuple list authorization": f"[('Authorization', 'Basic {CANARY}')]",
    "nested cookie tuple": f"(('cookie', 'a={CANARY}'),)",
    "pwd assignment": f"pwd={CANARY}",
    "auth assignment": f"auth={CANARY}",
    "cli flag with space": f"deeper-dive --api-key {CANARY} run",
    "cli password flag": f"tool --password {CANARY}",
    "cli password equals": f"tool --password={CANARY}",
    "xml element": f"<password>{CANARY}</password>",
    "xml element with attribute": f'<apiKey type="x">{CANARY}</apiKey>',
    "quoted value with a space": f'password="pa ss{CANARY}"',
    "quoted value with a space and colon": f"secret: 'two words {CANARY}'",
    "unclosed quoted value with a space": f'password="pa ss{CANARY}',
    "escaped json apiKey": '"{\\"apiKey\\":\\"' + CANARY + '\\"}"',
    "escaped json spaced password": '"\\"password\\" : \\"' + CANARY + '\\""',
}


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_credential_shape_is_redacted(name: str) -> None:
    text = LEAKS[name]
    assert CANARY not in str(redact(text)), name
    assert CANARY not in sanitize_exception_message(RuntimeError(f"failed: {text}")), name


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_credential_shape_is_redacted_inside_a_repr(name: str) -> None:
    assert CANARY not in str(redact(repr(LEAKS[name]))), name


BENIGN = [
    "{b'content-type': b'json'}",
    "('accept', 'text/html')",
    "--verbose",
    "--max-tokens 4 --output out.txt",
    "auth_method=oauth",
    "author=Bob",
    "<author>Bob</author>",
    '<title type="x">Hello</title>',
    'say "password reset" to continue',
    "{'a': 1, 'token_count': 3}",
    'status="ok done"',
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_round_trips(text: str) -> None:
    assert redact(text) == text


def test_redacted_text_keeps_the_surrounding_shape() -> None:
    assert redact("[('x-api-key', 'C'), ('accept', 'json')]") == (
        "[('x-api-key', '[REDACTED]'), ('accept', 'json')]"
    )
    assert redact("--api-key C --verbose") == "--api-key [REDACTED] --verbose"
    assert redact("<user>bob</user><password>C</password>") == (
        "<user>bob</user><password>[REDACTED]</password>"
    )


@pytest.mark.parametrize(
    "text",
    [
        "use '-----BEGIN PRIVATE KEY-----' header",
        "see -----BEGIN PRIVATE KEY----- header for the format",
    ],
)
def test_prose_naming_a_pem_header_survives(text: str) -> None:
    assert redact(text) == text


@pytest.mark.parametrize(
    "text",
    [
        f"-----BEGIN PRIVATE KEY-----\n{CANARY}AAAAAAAAAAAAAAAA\n-----END PRIVATE KEY-----",
        f"-----BEGIN PRIVATE KEY----- {CANARY}AAAAAAAAAAAAAAAA -----END PRIVATE KEY-----",
        f"x\\n-----BEGIN RSA PRIVATE KEY-----\\n{CANARY}AAAA",
        f"-----BEGIN PGP PRIVATE KEY BLOCK-----\nVersion: 1\n\n{CANARY}",
        f"-----BEGIN PRIVATE KEY-----\n{CANARY}",
    ],
)
def test_pem_bodies_are_still_redacted(text: str) -> None:
    assert CANARY not in str(redact(text))


def test_credential_shaped_fragment_is_redacted_on_purpose() -> None:
    # ``h:abc#frag@x.com`` has the same shape as ``user:pass#word@host``; it fails closed.
    assert "frag" not in str(redact("http://h:abc#frag@x.com"))
