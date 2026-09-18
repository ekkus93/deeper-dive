from __future__ import annotations

from pathlib import Path

from deeper_dive.parsing import ParseRequest, ParseSeverity, PdfParser, validate_parse_result


def test_pdf_parser_extracts_text_with_page_provenance(tmp_path: Path) -> None:
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(_pdf_bytes(["First page text", "Second page text"]))

    parser = PdfParser()
    result = parser.parse(ParseRequest(path=pdf))

    validate_parse_result(parser, result)
    assert not result.has_errors
    assert result.metadata["format"] == "pdf"
    assert result.metadata["library"] == "pypdf"
    assert result.metadata["page_count"] == "2"
    assert [block.location for block in result.blocks] == ["page:1", "page:2"]
    assert result.blocks[0].metadata == {"kind": "page", "page": "1"}
    assert "First page text" in result.blocks[0].text
    assert "Second page text" in result.blocks[1].text


def test_pdf_parser_warns_for_image_only_or_empty_pages(tmp_path: Path) -> None:
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(_blank_pdf_bytes())

    result = PdfParser().parse(ParseRequest(path=pdf))

    assert result.blocks == ()
    assert not result.has_errors
    assert {diagnostic.code for diagnostic in result.diagnostics} == {
        "page-no-text",
        "image-only-or-empty-pdf",
    }
    assert all(diagnostic.severity is ParseSeverity.WARNING for diagnostic in result.diagnostics)


def test_pdf_parser_reports_malformed_pdf(tmp_path: Path) -> None:
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")

    result = PdfParser().parse(ParseRequest(path=pdf))

    assert result.blocks == ()
    assert result.has_errors
    assert result.diagnostics[0].code == "malformed-pdf"


def _pdf_bytes(page_texts: list[str]) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 6 0 R] /Count 2 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        _stream(f"BT /F1 12 Tf 72 720 Td ({page_texts[0]}) Tj ET".encode()),
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 7 0 R >>"
        ),
        _stream(f"BT /F1 12 Tf 72 720 Td ({page_texts[1]}) Tj ET".encode()),
    ]
    return _build_pdf(objects)


def _blank_pdf_bytes() -> bytes:
    return _build_pdf(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        ]
    )


def _stream(content: bytes) -> bytes:
    return b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"


def _build_pdf(objects: list[bytes]) -> bytes:
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(output)
