"""TPR-19.1: diagnostic redaction stays fast on adversarial input."""

from __future__ import annotations

import signal
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from deeper_dive.diagnostics import MAX_REDACTED_TEXT_CHARS, redact

_N = 10_000
_BOUND_SECONDS = 0.5
_HARD_LIMIT_SECONDS = 10

_CASES = {
    "auth_quoted_escapes": '"authorization": "' + "\\a" * (_N // 2),
    "auth_quoted_backslashes": '"authorization": "' + "\\" * _N,
    "auth_field_redacted_run": "authorization: " + "[REDACTED]" * (_N // 10),
    "assignment_run": "token" * (_N // 5),
    "assignment_dotted": "a." * (_N // 2) + "token=x",
    "quoted_mapping_unterminated": "'api_key': '" + "x" * _N,
    "quoted_mapping_escapes": "'api_key': '" + "\\x" * (_N // 2),
    "container_open": "'token': [" * (_N // 10),
    "container_quotes": "'token': [" + "'a'," * (_N // 4),
    "url_userinfo": "http://" + "a" * _N,
    "url_fragment": "http://h/" + "a" * _N + "#" + "b" * _N,
    "encoded_url": "http" + "%25" * (_N // 3) + "3a%2f%2f",
    "encoded_query": "?" + "a=b&" * (_N // 4),
    "many_urls": "https://u:p@h/?token=x#f " * (_N // 25),
    "digest": "authorization: digest " + "a," * (_N // 2),
    "bearer": "bearer " + "a" * _N,
    "plain": "x" * _N,
    "alnum_run_no_scheme": "a1" * (_N // 2),
    "repeated_scheme_prefix": "http://" * (_N // 7),
    "percent_encoded_url": "https://h/" + "%23" * (_N // 3),
    "long_partly_encoded_urls": "https://h/a%23b " * (_N // 16),
}


@contextmanager
def _hard_limit() -> Iterator[None]:
    """Fail instead of hanging the suite if a pattern backtracks catastrophically."""
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def _timeout(signum: int, frame: object) -> None:
        raise TimeoutError("redact() exceeded the hard time limit")

    previous = signal.signal(signal.SIGALRM, _timeout)
    signal.alarm(_HARD_LIMIT_SECONDS)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@pytest.mark.parametrize("name", sorted(_CASES))
def test_redact_adversarial_input_is_fast(name: str) -> None:
    with _hard_limit():
        started = time.perf_counter()
        redact(_CASES[name])
        elapsed = time.perf_counter() - started
    assert elapsed < _BOUND_SECONDS, f"{name} took {elapsed:.3f}s"


def test_unterminated_quoted_authorization_with_escapes_is_still_redacted_when_closed() -> None:
    text = '{"authorization": "Basic abc\\"def", "ok": 1}'
    result = redact(text)
    assert isinstance(result, str)
    assert "abc" not in result
    assert '"ok": 1' in result


def test_oversized_text_is_truncated_before_redaction() -> None:
    secret_tail = "token=CANARY-SECRET"
    result = redact("x" * (MAX_REDACTED_TEXT_CHARS + 10) + secret_tail)
    assert isinstance(result, str)
    assert "CANARY-SECRET" not in result
    assert result.endswith("[TRUNCATED]")
    assert len(result) < MAX_REDACTED_TEXT_CHARS + 100


_CAP = MAX_REDACTED_TEXT_CHARS - 1_000
_CAP_CASES = {
    "scheme_repeat": "http://" * (_CAP // 7),
    "https_scheme_repeat": "https://" * (_CAP // 8),
    "encoded_scheme_repeat": "https%3A%2F%2Fa.com%2F%3Fa%3D" * (_CAP // 29),
    "fragment_repeat": "http://a/#access_token=abc " * (_CAP // 27),
    "url_hash_repeat": "http://a#" * (_CAP // 9),
    "bare_key_repeat": "sk-" * (_CAP // 3),
    "userinfo_repeat": "http://u:p@" * (_CAP // 11),
}


@pytest.mark.parametrize("name", sorted(_CAP_CASES))
def test_redact_stays_fast_at_the_input_cap(name: str) -> None:
    """The reviewer found a 28 s case below the cap that the 10 KB cases above missed."""
    with _hard_limit():
        started = time.perf_counter()
        redact(_CAP_CASES[name])
        elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"{name} took {elapsed:.2f}s at {len(_CAP_CASES[name])} chars"


@pytest.mark.parametrize(
    "text",
    [
        "http://h/?session=SECRETVAL&a=1",
        "http://h/?jwt=SECRETVAL",
        "http://h/?credential=SECRETVAL",
        "http://h/?pass=SECRETVAL",
        "http://h/?pwd=SECRETVAL",
        "http://h/?X-Amz-Credential=SECRETVAL",
        "failed with key sk-ant-api03-SECRETVALUE1234567890",
        "sk-proj-SECRETVALUE1234567890abcdef",
    ],
)
def test_additional_credential_shapes_are_redacted(text: str) -> None:
    assert "SECRETVAL" not in str(redact(text))


def test_short_sk_prefixed_words_are_not_treated_as_keys() -> None:
    assert redact("task sk-short is fine") == "task sk-short is fine"
