from __future__ import annotations

import zipfile
from pathlib import Path

from deeper_dive.parsing import DocxParser, ParseRequest, validate_parse_result


def _write_docx(path: Path, body: str) -> None:
    document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{body}</w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document)


def test_docx_round_trips_title_headings_and_body(tmp_path: Path) -> None:
    path = tmp_path / "fixture.docx"
    _write_docx(
        path,
        """
<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr>
<w:r><w:t>Document Title</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
<w:r><w:t>Section One</w:t></w:r></w:p>
<w:p><w:r><w:t>Body text</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>
<w:r><w:t>Details</w:t></w:r></w:p>
<w:p><w:r><w:t>More text</w:t></w:r></w:p>
""",
    )
    parser = DocxParser()
    result = parser.parse(ParseRequest(path=path))
    validate_parse_result(parser, result)

    assert [block.text for block in result.blocks] == [
        "Document Title",
        "Section One",
        "Body text",
        "Details",
        "More text",
    ]
    assert [block.heading for block in result.blocks] == [
        None,
        "Section One",
        "Section One",
        "Details",
        "Details",
    ]
    assert result.blocks[0].metadata["style"] == "Title"
    assert result.blocks[1].metadata["kind"] == "heading"
    assert result.blocks[2].location == "paragraph:3"
    assert not result.has_errors


def test_malformed_docx_is_reported_cleanly(tmp_path: Path) -> None:
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a zip")
    result = DocxParser().parse(ParseRequest(path=path))
    assert result.has_errors
    assert result.diagnostics[0].code == "malformed-docx"


def test_docx_missing_document_body_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "empty.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("other.xml", "<root />")
    result = DocxParser().parse(ParseRequest(path=path))
    assert result.has_errors
    assert result.diagnostics[0].code == "malformed-docx"
