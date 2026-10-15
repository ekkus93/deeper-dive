"""7PR-03: credential spellings and neighboring benign text."""

from __future__ import annotations

import json
import time
from itertools import combinations

import pytest

from deeper_dive.diagnostics import MAX_REDACTED_TEXT_CHARS, redact

CANARY = "CANARY9x"

LEAKS = {
    "URL trailing slash": f"https://user:p/{CANARY}/@host",
    "URL empty user trailing slash": f"redis://:p/{CANARY}/@host",
    "URL slash password authority": f"https://user:p{CANARY}/@host/x",
    "header list of lists": repr([["x-api-key", CANARY]]),
    "header spaced list": "[ 'x-api-key' , " + repr(CANARY) + " ]",
    "header bytes lists": repr([[b"x-api-key", CANARY.encode()]]),
    **{
        f"flag {name}": f"--{name} {CANARY}"
        for name in (
            "apikey",
            "accesstoken",
            "clientsecret",
            "privatekey",
            "pass",
            "passphrase",
            "credentials",
            "db-pass",
            "key",
        )
    },
    "assignment DB_PASS": f"DB_PASS={CANARY}",
    "assignment pass": f"pass={CANARY}",
    "assignment passphrase": f"passphrase={CANARY}",
    "assignment credentials": f"credentials={CANARY}",
    "assignment sessionid": f"sessionid={CANARY}",
    "escaped quoted JSON": r"{\"api_key\": \"a\\\"" + CANARY + r"\"}",
}


@pytest.mark.parametrize("shape", sorted(LEAKS))
def test_seventh_cycle_credential_shapes_are_redacted(shape: str) -> None:
    assert CANARY not in str(redact(LEAKS[shape])), shape
    assert CANARY not in str(redact({"detail": [LEAKS[shape]]})), shape


def test_credential_nouns_agree_across_assignment_mapping_flag_and_element() -> None:
    for name in ("passphrase", "sessionid", "clientsecret", "apikey"):
        forms = (
            f"{name}={CANARY}",
            json.dumps({name: CANARY}),
            f"--{name} {CANARY}",
            f"<{name}>{CANARY}</{name}>",
        )
        assert all(CANARY not in str(redact(form)) for form in forms), name


def test_nested_header_pair_objects_redact_the_value() -> None:
    assert redact([["x-api-key", CANARY]]) == [["x-api-key", "[REDACTED]"]]
    assert redact([(b"x-api-key", CANARY.encode())]) == [[b"x-api-key", "[REDACTED]"]]


@pytest.mark.parametrize(
    "text",
    [
        "https://registry.npmjs.org/@scope/package",
        "https://git.example/repo/@v1",
        "https://host:8080/@x",
        "password_policy=strict",
        "passenger=3",
        "--passenger-count 2",
        "compass=north",
        "--token-count 5",
        "--pwd-dir /tmp/pwd",
        "--max-tokens 100",
        "-p 3",
    ],
)
def test_nearby_benign_shapes_are_unchanged(text: str) -> None:
    assert redact(text) == text


def test_mixed_redaction_pass_pairs_scale_linearly() -> None:
    prefixes = (
        "token=CANARY9x;",
        r"{\"api_key\": \"value\\\"tail\"};",
        "https://service/path#access_token=CANARY9x;",
        "https://user:password/CANARY9x/@host;",
        "http%3A%2F%2Fuser%3Apass%40host;",
    )

    def elapsed(text: str) -> float:
        start = time.perf_counter()
        redact(text)
        return time.perf_counter() - start

    worst_cap_seconds = 0.0
    for first, second in combinations(prefixes, 2):

        def sample(size: int, first: str = first, second: str = second) -> str:
            unit = first + second
            return (unit * (size // len(unit) + 1))[:size]

        small = elapsed(sample(MAX_REDACTED_TEXT_CHARS // 4))
        middle = elapsed(sample(MAX_REDACTED_TEXT_CHARS // 2))
        large = elapsed(sample(MAX_REDACTED_TEXT_CHARS))
        worst_cap_seconds = max(worst_cap_seconds, large)
        assert middle <= max(3 * small, 0.25), (first, second, small, middle)
        assert large <= max(6 * small, 0.5), (first, second, small, large)
    assert worst_cap_seconds < 10.0
