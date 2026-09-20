from __future__ import annotations

import zipfile
from pathlib import Path

from pypdf import PdfWriter

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.batch_import import (
    DuplicateDisposition,
    plan_file_imports,
    plan_url_imports,
)
from deeper_dive.html_ingestion import HtmlUrlParser
from deeper_dive.parsing import (
    DocxParser,
    ParseRequest,
    PdfParser,
    SourceParser,
    TextMarkdownParser,
)
from deeper_dive.storage.workspace import WorkspaceManager


def _parsers() -> list[SourceParser]:
    return [TextMarkdownParser(), PdfParser(), DocxParser(), HtmlUrlParser()]


def _write_docx(path: Path) -> None:
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t>DOCX fixture</w:t></w:r></w:p></w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def test_file_parser_matrix_qualifies_pdf_docx_txt_markdown_and_html(
    tmp_path: Path,
) -> None:
    txt = tmp_path / "fixture.txt"
    markdown = tmp_path / "fixture.md"
    html = tmp_path / "fixture.html"
    docx = tmp_path / "fixture.docx"
    pdf = tmp_path / "fixture.pdf"
    txt.write_text("plain fixture", encoding="utf-8")
    markdown.write_text("# Fixture\nmarkdown body", encoding="utf-8")
    html.write_text(
        "<main><h1>Fixture</h1><p>HTML body</p></main>", encoding="utf-8"
    )
    _write_docx(docx)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf.open("wb") as stream:
        writer.write(stream)

    cases = (
        (TextMarkdownParser(), txt, "text"),
        (TextMarkdownParser(), markdown, "markdown"),
        (HtmlUrlParser(), html, "html"),
        (DocxParser(), docx, "docx"),
        (PdfParser(), pdf, "pdf"),
    )
    for parser, path, expected_format in cases:
        request = ParseRequest(path=path)
        assert parser.supports(request)
        result = parser.parse(request)
        assert not result.has_errors
        assert result.metadata["format"] == expected_format


def test_url_directory_and_duplicate_matrix(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    first = corpus / "first.txt"
    duplicate = corpus / "duplicate.md"
    first.write_text("same fixture", encoding="utf-8")
    duplicate.write_text("same fixture", encoding="utf-8")

    plan = plan_file_imports([corpus], _parsers())
    assert {candidate.disposition for candidate in plan.candidates} == {
        DuplicateDisposition.IMPORT,
        DuplicateDisposition.DUPLICATE_CONTENT,
    }

    url_plan = plan_url_imports(
        ["HTTPS://Example.COM:443/article?a=2&b=1#fragment"], HtmlUrlParser()
    )
    candidate = url_plan.candidates[0]
    assert candidate.disposition is DuplicateDisposition.IMPORT
    assert candidate.canonical_url == "https://example.com/article?a=2&b=1"


def test_pasted_text_and_excluded_source_handling(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Source matrix")
    source = service.add_pasted_source(project.id, "Pasted fixture", "pasted body")

    assert source.source_type == "pasted-text"
    assert service.list_source_chunks(project.id, source.id)[0].text == "pasted body"

    service.set_source_included(project.id, source.id, False)
    excluded = service.get_source(project.id, source.id)
    assert excluded is not None
    assert not excluded.included
