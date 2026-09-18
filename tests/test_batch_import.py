from __future__ import annotations

from pathlib import Path

from deeper_dive.batch_import import (
    DuplicateDisposition,
    canonicalize_url,
    plan_file_imports,
    plan_url_imports,
)
from deeper_dive.html_ingestion import HtmlUrlParser
from deeper_dive.parsing import DocxParser, PdfParser, SourceParser, TextMarkdownParser


def _parsers() -> list[SourceParser]:
    return [TextMarkdownParser(), PdfParser(), DocxParser(), HtmlUrlParser()]


def test_multiple_files_detect_duplicate_content(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.md"
    first.write_text("same\n", encoding="utf-8")
    second.write_text("same\n", encoding="utf-8")

    plan = plan_file_imports([first, second], _parsers())

    assert [candidate.disposition for candidate in plan.candidates] == [
        DuplicateDisposition.IMPORT,
        DuplicateDisposition.DUPLICATE_CONTENT,
    ]
    assert len(plan.importable) == 1
    assert plan.duplicates[0].reason == "duplicate content hash"


def test_existing_content_hash_prevents_reimport(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("already imported", encoding="utf-8")
    first_plan = plan_file_imports([source], _parsers())
    content_hash = first_plan.candidates[0].content_hash
    assert content_hash is not None

    second_plan = plan_file_imports([source], _parsers(), existing_content_hashes={content_hash})

    assert second_plan.candidates[0].disposition is DuplicateDisposition.DUPLICATE_CONTENT


def test_directory_import_recurses_and_filters_supported_extensions(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    nested = corpus / "nested"
    nested.mkdir(parents=True)
    supported = nested / "note.md"
    ignored = nested / "binary.bin"
    supported.write_text("# Heading\nbody", encoding="utf-8")
    ignored.write_bytes(b"\x00\x01")

    plan = plan_file_imports([corpus], _parsers())

    by_title = {candidate.title: candidate for candidate in plan.candidates}
    assert by_title["note.md"].disposition is DuplicateDisposition.IMPORT
    assert by_title["binary.bin"].disposition is DuplicateDisposition.UNSUPPORTED


def test_canonical_url_duplicates_are_presented_before_fetch() -> None:
    plan = plan_url_imports(
        [
            "HTTPS://Example.COM:443/articles?a=2&b=1#section",
            "https://example.com/articles?b=1&a=2",
        ],
        HtmlUrlParser(),
    )

    assert plan.candidates[0].canonical_url == "https://example.com/articles?a=2&b=1"
    assert plan.candidates[0].disposition is DuplicateDisposition.IMPORT
    assert plan.candidates[1].disposition is DuplicateDisposition.DUPLICATE_URL


def test_existing_canonical_url_prevents_duplicate_url_import() -> None:
    plan = plan_url_imports(
        ["http://example.com:80/path"],
        HtmlUrlParser(),
        existing_canonical_urls={"http://example.com/path"},
    )

    assert plan.candidates[0].disposition is DuplicateDisposition.DUPLICATE_URL


def test_invalid_url_is_non_importable() -> None:
    assert canonicalize_url("ftp://example.com/file") is None
    plan = plan_url_imports(["not a url"], HtmlUrlParser())
    assert plan.candidates[0].disposition is DuplicateDisposition.UNSUPPORTED
    assert not plan.candidates[0].should_import
