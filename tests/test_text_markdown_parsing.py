from __future__ import annotations

import hashlib
from pathlib import Path

from deeper_dive.parsing import ParseRequest, TextMarkdownParser, validate_parse_result


def test_plain_text_utf8_unicode_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    text = "café 日本語 🧪\nsecond line\n"
    path.write_text(text, encoding="utf-8")
    parser = TextMarkdownParser()
    result = parser.parse(ParseRequest(path=path))
    validate_parse_result(parser, result)
    assert [block.text for block in result.blocks] == ["café 日本語 🧪", "second line"]
    assert [block.location for block in result.blocks] == ["line:1", "line:2"]
    assert result.metadata["content_hash"] == hashlib.sha256(text.encode()).hexdigest()
    assert not result.has_errors


def test_markdown_retains_heading_context(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Intro\nBody\n## Detail\nMore\n", encoding="utf-8")
    result = TextMarkdownParser().parse(ParseRequest(path=path))
    assert [block.heading for block in result.blocks] == ["Intro", "Intro", "Detail", "Detail"]
    assert [block.metadata["kind"] for block in result.blocks] == [
        "heading",
        "paragraph",
        "heading",
        "paragraph",
    ]


def test_pasted_text_and_empty_input_are_supported() -> None:
    parser = TextMarkdownParser()
    pasted = parser.parse(ParseRequest(text="Pasted Ω", media_type="text/plain"))
    empty = parser.parse(ParseRequest(text="", media_type="text/plain"))
    assert pasted.blocks[0].text == "Pasted Ω"
    assert empty.blocks == ()
    assert empty.metadata["content_hash"] == hashlib.sha256(b"").hexdigest()


def test_invalid_utf8_and_unsupported_encoding_are_explicit(tmp_path: Path) -> None:
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\xff\xfe\x00")
    result = TextMarkdownParser().parse(ParseRequest(path=path))
    assert result.has_errors
    assert result.diagnostics[0].code == "invalid-utf8"


def test_duplicate_content_has_identical_hash(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.md"
    first.write_text("same", encoding="utf-8")
    second.write_text("same", encoding="utf-8")
    parser = TextMarkdownParser()
    a = parser.parse(ParseRequest(path=first))
    b = parser.parse(ParseRequest(path=second))
    assert a.metadata["content_hash"] == b.metadata["content_hash"]


def test_unsupported_file_type_reports_error(tmp_path: Path) -> None:
    path = tmp_path / "notes.bin"
    path.write_bytes(b"data")
    result = TextMarkdownParser().parse(ParseRequest(path=path))
    assert result.has_errors
    assert result.diagnostics[0].code == "unsupported-type"
