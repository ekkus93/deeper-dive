"""FPR-08: sanitizer leaks found in the fourth review, benign text, and linear time."""

from __future__ import annotations

import time

import pytest

from deeper_dive.diagnostics import MAX_REDACTED_TEXT_CHARS, redact

CANARY = "CANARY9x"

# (id, text) — every input must come back without the canary.
LEAKS = {
    "empty username userinfo": f"redis://:{CANARY}@localhost:6379/0",
    "at sign in password": f"https://user:p@{CANARY}@host/x",
    "slash in password": f"postgresql://app:ab/{CANARY}+e==@db:5432/x",
    "username only": f"https://{CANARY}@host/x",
    "wss encoded separator": f"wss://h/p?token%3D{CANARY}",
    "wss encoded ampersand": f"wss://h/p?x=1%26token%3D{CANARY}",
    "custom scheme fragment": f"myapp://cb#code={CANARY}",
    "custom scheme query": f"myapp://cb?access_token={CANARY}",
    "unclosed double-quoted authorization": f'{{"authorization": "Basic {CANARY}',
    "unclosed single-quoted authorization": f"{{'Authorization': 'Basic {CANARY}",
    "paren in fragment value": f"https://h/cb#access_token=ab)c{CANARY}",
    "azure subscription key header": f"{{'Ocp-Apim-Subscription-Key': '{CANARY}'}}",
    "comma list of urls": f"https://a:b@h1,https://c:{CANARY}@h2",
    "capped input cut mid authorization": '"authorization": "'
    + "x" * (MAX_REDACTED_TEXT_CHARS)
    + CANARY,
}


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_no_canary_survives(name: str) -> None:
    assert CANARY not in str(redact(LEAKS[name])), name


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_no_canary_survives_in_nested_values(name: str) -> None:
    assert CANARY not in str(redact({"detail": [LEAKS[name]]})), name


def test_comma_ends_a_fragment_value() -> None:
    assert redact("see https://h/x#access_token=C, then") == "see https://h/x#[REDACTED], then"
    assert redact("{url: https://h/x#access_token=C,k:1}") == "{url: https://h/x#[REDACTED],k:1}"


def test_closing_bracket_of_an_enclosing_context_still_ends_the_fragment() -> None:
    assert redact("[a](https://h/x#access_token=C) tail") == "[a](https://h/x#[REDACTED]) tail"
    assert redact("(see https://h/x#access_token=C) ok") == "(see https://h/x#[REDACTED]) ok"
    assert redact('{"u": "https://h/x#access_token=C"} z') == '{"u": "https://h/x#[REDACTED]"} z'


BENIGN = [
    "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Authorization#credentials",
    "https://example.com/docs#session",
    "https://example.com/docs#token-limits",
    "https://example.com/docs#password",
    "https://example.com/a?lang=en&page=2#section:overview",
    "see https://example.com/page, then continue",
    "mailto:someone@example.com",
    "https://example.com/users/a@b.com/profile?mail=a@b.com",
    "plain prose with an email a@b.com and a path /usr/local/bin",
    "scheme-less host:8080/path and C:\\temp\\file",
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_text_is_unchanged(text: str) -> None:
    assert redact(text) == text


_N = 10_000
SHAPES = {
    "userinfo_many_ats": "http://" + "a@" * (_N // 2),
    "userinfo_many_colons": "http://" + "a:" * (_N // 2) + "@h",
    "userinfo_slashes": "http://" + "a:b/" * (_N // 4) + "@h",
    "repeated_schemes_at": "ftp://" * (_N // 6) + "@",
    "custom_scheme_fragments": "myapp://x#code=1 " * (_N // 17),
    "unclosed_auth_many": '"authorization": "' * (_N // 17),
    "fragment_parens": "https://h/#a=" + ")" * _N,
    "fragment_openers": "(" * _N + " https://h/#a=" + ")" * 10,
    "long_comma_list": ",".join(["https://u:p@h"] * (_N // 14)),
}


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_linear_time_on_adversarial_shapes(name: str) -> None:
    text = SHAPES[name]
    redact(text)  # warm
    start = time.perf_counter()
    redact(text)
    small = time.perf_counter() - start
    big_text = text * 8
    start = time.perf_counter()
    redact(big_text)
    big = time.perf_counter() - start
    assert big < 1.5, (name, big)
    # 8x the input must not cost wildly more than 8x (quadratic would be ~64x).
    assert big < max(small, 0.005) * 8 * 6, (name, small, big)


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_new_shapes_stay_fast_at_the_input_cap(name: str) -> None:
    text = (SHAPES[name] * (MAX_REDACTED_TEXT_CHARS // len(SHAPES[name]) + 1))[
        :MAX_REDACTED_TEXT_CHARS
    ]
    start = time.perf_counter()
    redact(text)
    assert time.perf_counter() - start < 3.0, name
