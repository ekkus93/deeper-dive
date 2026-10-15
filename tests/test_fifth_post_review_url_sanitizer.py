"""5PR-01 / 5PR-06: credential URLs with terminators in the password; benign JSON/code intact."""

from __future__ import annotations

import json

import pytest
from linear_timing import assert_scales_linearly

from deeper_dive.diagnostics import MAX_REDACTED_TEXT_CHARS, redact, sanitize_exception_message

CANARY = "CANARY9x"

LEAKS = {
    "hash in password": f"https://user:pa#ss{CANARY}@host/x",
    "question mark in password": f"https://user:pa?ss{CANARY}@host/x",
    "single quote in password": f"postgres://user:pa'{CANARY}@db/x",
    "double quote in password": f'https://user:{CANARY}"@host',
    "less-than in password": f"https://user:pa<ss{CANARY}@host/x",
    "greater-than in password": f"https://user:pa>ss{CANARY}@host/x",
}


def _shapes() -> dict[str, str]:
    shapes: dict[str, str] = {}
    for name, url in LEAKS.items():
        shapes[name] = url
        shapes[f"{name} in a repr"] = f"DatabaseError({url!r})"
        shapes[f"{name} after text"] = f"connect failed for {url} (retrying)"
        shapes[f"{name} in json"] = json.dumps({"dsn": url, "ok": True})
    return shapes


SHAPES = _shapes()


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_terminators_in_a_password_do_not_leak(name: str) -> None:
    assert CANARY not in str(redact(SHAPES[name])), name
    assert CANARY not in sanitize_exception_message(RuntimeError(SHAPES[name])), name


def test_terminators_in_a_password_do_not_leak_inside_json() -> None:
    text = '{"dsn": "https://user:pa#ss' + CANARY + '@host/x", "ok": true}'
    assert CANARY not in str(redact(text))


BENIGN = [
    '{"url":"http://localhost:8080/x","email":"a@b.com"}',
    "fetch('http://api:8080/v1/x').catch(e=>log('a@b.com'))",
    "see http://host:8080?email=a@b.com for details",
    "see http://host:8080#mail@b.com for details",
    '<a href="http://host:80">me@x.com</a>',
    '{"u":"http://host","e":"a@b.com"}',
    "https://example.com/path?next=/a@b",
    "contact me@example.com about https://example.com/docs",
]


@pytest.mark.parametrize("text", BENIGN)
def test_benign_json_and_code_round_trip(text: str) -> None:
    assert redact(text) == text


def test_slash_in_password_still_redacted() -> None:
    assert CANARY not in str(redact(f"postgresql://app:ab/{CANARY}+e==@db:5432/x"))


def test_new_shapes_stay_linear_at_the_cap() -> None:
    for filler in ("https://u:" + "#" * 500, "https://u:" + "?'" * 250, "https://" + "a:" * 300):

        def make(size: int, filler: str = filler) -> str:
            return (filler * (size // len(filler) + 1))[:size]

        assert_scales_linearly(redact, make, large=MAX_REDACTED_TEXT_CHARS, label=filler[:20])


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_terminators_in_a_password_do_not_leak_through_the_cli(
    name: str,
    tmp_path,
    capsys,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    from deeper_dive.cli import main

    def failing(*_args: object) -> int:
        raise RuntimeError(f"upstream failed for {LEAKS[name]}")

    monkeypatch.setattr("deeper_dive.cli._project_command", failing)
    assert main(["--data-dir", str(tmp_path / "data"), "project", "list"]) == 2
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err
