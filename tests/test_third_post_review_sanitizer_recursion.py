"""TPR-19: redact() never recurses without bound on URLs containing a bare percent sign."""

from __future__ import annotations

import random

import pytest

from deeper_dive.diagnostics import redact


@pytest.mark.parametrize(
    "text",
    [
        "see http://example.com/100% done",
        "http://h/?%",
        "http://h/a%zz",
        "https://x/%",
        "ftp://x/50%",
    ],
)
def test_bare_percent_in_a_url_is_left_intact_and_does_not_recurse(text: str) -> None:
    assert redact(text) == text


@pytest.mark.parametrize("layers", [10, 300, 3000])
def test_deeply_layered_encoding_terminates(layers: int) -> None:
    redact("http://h/?" + "%25" * layers)
    redact("https%3A%2F%2Fh%2F" + "%2525" * layers)


def test_credentials_inside_layered_encoding_are_still_redacted() -> None:
    assert "abc123" not in str(redact("https%3A%2F%2Fh%2F%3Ftoken%3Dabc123"))
    assert "abc123" not in str(redact("http://h/?token=abc123&x=1"))


def test_adversarial_mixed_fragments_never_raise() -> None:
    seeds = ["a=", '"', "'", "%25", "://", "@", "#", "&", "token=", "http://", "%", "[", "/", "?"]
    rng = random.Random(1)
    for _ in range(25):
        redact("".join(rng.choice(seeds) for _ in range(3000)))
