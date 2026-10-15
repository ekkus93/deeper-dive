"""6PR-02: credential URLs whose password mixes terminators with ``@``, ``/``, ``,``, ``)``, quotes."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from deeper_dive.cli import main
from deeper_dive.diagnostics import MAX_REDACTED_TEXT_CHARS, redact, sanitize_exception_message

CANARY = "CANARY9x"

LEAKS = {
    "at then hash": f"https://user:p@a#ss{CANARY}@host/x",
    "slash then question": f"https://user:pa/ss?{CANARY}@host/x",
    "slash path then question": f"https://user:{CANARY}/x?y@host",
    "slash then single quote": f"https://user:pa/ss'{CANARY}@host/x",
    "slash then double quote": f'https://user:pa/ss"{CANARY}@host/x',
    "hash then comma": f"https://user:pa#ss,{CANARY}@host",
    "question then paren": f"https://user:{CANARY}?)x@host",
    "slash then paren": f"https://user:{CANARY}/x)y@host",
    "long password with a hash": f"https://user:{'a' * 1500}#{CANARY}@host/x",
    "port-like but too large": f"https://user:123456#{CANARY}@host",
}


def _shapes() -> dict[str, str]:
    shapes: dict[str, str] = {}
    for name, url in LEAKS.items():
        shapes[name] = url
        shapes[f"{name} in a repr"] = f"DatabaseError({url!r})"
        shapes[f"{name} after text"] = f"connect failed for {url} (retrying)"
        shapes[f"{name} in json"] = '{"dsn": "' + url.replace('"', '\\"') + '", "ok": true}'
    return shapes


SHAPES = _shapes()


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_terminator_combinations_do_not_leak(name: str) -> None:
    assert CANARY not in str(redact(SHAPES[name])), name
    assert CANARY not in sanitize_exception_message(RuntimeError(SHAPES[name])), name


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_cli_error_path_does_not_leak(
    name: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The CLI's catch-all prints ``sanitize_exception_message``; make a command raise
    # an error whose message carries the URL (real commands only echo generic text).
    def failing(*_args: object) -> int:
        raise RuntimeError(f"upstream failed for {LEAKS[name]}")

    monkeypatch.setattr("deeper_dive.cli._project_command", failing)
    code = main(["--data-dir", str(tmp_path / "data"), "project", "list"])
    captured = capsys.readouterr()
    assert code == 2
    assert CANARY not in captured.out + captured.err


BENIGN = [
    "see http://host:8080?email=a@b.com for details",
    "see http://host:8080#mail@b.com for details",
    "https://example.com/path?next=/a@b",
    "https://host:8080/v1/models/gpt@latest",
    "scheme://host:8080/@scope/x",
    "https://example.com?q=a:b@c",
    "https://example.com#a:b@c",
    "https://pypi.org/simple/pkg@1.0",
    '{"u":"https://h:8080/x","e":"a@b.com"}',
    "contact me@example.com about https://example.com/docs",
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_urls_round_trip(text: str) -> None:
    assert redact(text) == text


@pytest.mark.xfail(strict=True, reason="accepted: password starting with a valid port number")
@pytest.mark.parametrize(
    "url", [f"https://user:8#{CANARY}@host", f"https://user:2024#{CANARY}@host"]
)
def test_accepted_gap_password_starting_with_a_port_number(url: str) -> None:
    # Indistinguishable from ``host:8080#mail@b.com``; flips visibly if it is ever fixed.
    assert CANARY not in str(redact(url))


def test_terminator_combinations_scale_linearly_at_the_cap() -> None:
    fillers = (
        "https://u:" + "#" * 500,
        "https://u:" + "?'" * 250,
        "u://a#@",
        "x://",
        "https://u:,)",
    )

    def worst(size: int) -> float:
        best = 0.0
        for filler in fillers:
            text = (filler * (size // len(filler) + 1))[:size]
            start = time.perf_counter()
            redact(text)
            best = max(best, time.perf_counter() - start)
        return best

    small, large = worst(MAX_REDACTED_TEXT_CHARS // 4), worst(MAX_REDACTED_TEXT_CHARS)
    # Quadratic behaviour would give ~16x; allow generous noise around the linear 4x.
    assert large < max(8 * small, 0.5) + 2.0
