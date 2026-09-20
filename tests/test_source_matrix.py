# fmt: off
from __future__ import annotations

import zipfile
from pathlib import Path

from pypdf import PdfWriter

import deeper_dive.batch_import as batch
import deeper_dive.parsing as parsing
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.html_ingestion import HtmlUrlParser
from deeper_dive.storage.workspace import WorkspaceManager


def _parsers() -> list[parsing.SourceParser]:
    return [parsing.TextMarkdownParser(), parsing.PdfParser(), parsing.DocxParser(), HtmlUrlParser()]


def _docx(path: Path) -> None:
    xml = '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>DOCX fixture</w:t></w:r></w:p></w:body></w:document>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)


def test_file_source_matrix(tmp_path: Path) -> None:
    txt = tmp_path / "a.txt"
    md = tmp_path / "b.md"
    html = tmp_path / "c.html"
    docx = tmp_path / "d.docx"
    pdf = tmp_path / "e.pdf"
    txt.write_text("plain", encoding="utf-8")
    md.write_text("# Markdown", encoding="utf-8")
    html.write_text("<main>HTML</main>", encoding="utf-8")
    _docx(docx)
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with pdf.open("wb") as stream:
        writer.write(stream)
    cases = [
        (parsing.TextMarkdownParser(), txt, "text"),
        (parsing.TextMarkdownParser(), md, "markdown"),
        (HtmlUrlParser(), html, "html"),
        (parsing.DocxParser(), docx, "docx"),
        (parsing.PdfParser(), pdf, "pdf"),
    ]
    for parser, path, expected in cases:
        result = parser.parse(parsing.ParseRequest(path=path))
        assert not result.has_errors
        assert result.metadata["format"] == expected


def test_batch_url_and_duplicate_matrix(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("same", encoding="utf-8")
    (corpus / "b.md").write_text("same", encoding="utf-8")
    plan = batch.plan_file_imports([corpus], _parsers())
    dispositions = [item.disposition for item in plan.candidates]
    assert batch.DuplicateDisposition.IMPORT in dispositions
    assert batch.DuplicateDisposition.DUPLICATE_CONTENT in dispositions
    urls = ["HTTPS://Example.COM:443/article?a=2&b=1#fragment"]
    url_plan = batch.plan_url_imports(urls, HtmlUrlParser())
    assert url_plan.candidates[0].canonical_url == "https://example.com/article?a=2&b=1"


def test_pasted_and_excluded_source_matrix(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Source matrix")
    source = service.add_pasted_source(project.id, "Pasted", "body")
    assert source.source_type == "pasted-text"
    assert service.list_source_chunks(project.id, source.id)[0].text == "body"
    service.set_source_included(project.id, source.id, False)
    excluded = service.get_source(project.id, source.id)
    assert excluded is not None
    assert not excluded.included
# fmt: on
