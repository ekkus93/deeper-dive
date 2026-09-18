"""Normalized parser contracts and baseline source ingestion."""

from __future__ import annotations

import hashlib
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree


class ParseSeverity(StrEnum):
    """Severity of a parser diagnostic."""

    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ParseDiagnostic:
    """A user-visible parser warning or error without provider-specific exceptions."""

    severity: ParseSeverity
    code: str
    message: str
    location: str | None = None


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    """One ordered structural unit emitted by a parser."""

    ordinal: int
    text: str
    location: str | None = None
    heading: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ParseResult:
    """Normalized parser output with identity needed for cache invalidation."""

    parser_id: str
    parser_version: str
    blocks: tuple[ParsedBlock, ...]
    diagnostics: tuple[ParseDiagnostic, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        return any(item.severity is ParseSeverity.ERROR for item in self.diagnostics)

    @property
    def cache_identity(self) -> str:
        return f"{self.parser_id}:{self.parser_version}"


@dataclass(frozen=True, slots=True)
class ParseRequest:
    """Input passed to a parser implementation."""

    path: Path | None = None
    text: str | None = None
    media_type: str | None = None

    def __post_init__(self) -> None:
        if (self.path is None) == (self.text is None):
            raise ValueError("parse request requires exactly one of path or text")


class SourceParser(Protocol):
    """Contract implemented by concrete source parsers."""

    @property
    def parser_id(self) -> str: ...

    @property
    def parser_version(self) -> str: ...

    def supports(self, request: ParseRequest) -> bool: ...

    def parse(self, request: ParseRequest) -> ParseResult: ...


def validate_parse_result(parser: SourceParser, result: ParseResult) -> None:
    """Reject malformed adapter output before it reaches persistence/chunking."""

    if result.parser_id != parser.parser_id or result.parser_version != parser.parser_version:
        raise ValueError("parse result identity does not match parser")
    ordinals = [block.ordinal for block in result.blocks]
    if ordinals != list(range(len(ordinals))):
        raise ValueError("parsed block ordinals must be contiguous and zero-based")


class TextMarkdownParser:
    """Deterministic UTF-8 parser for plain text, Markdown, and pasted text."""

    parser_id = "text-markdown"
    parser_version = "1"
    _extensions = frozenset({".txt", ".md", ".markdown"})

    def supports(self, request: ParseRequest) -> bool:
        if request.text is not None:
            return request.media_type in {None, "text/plain", "text/markdown"}
        assert request.path is not None
        return request.path.suffix.lower() in self._extensions

    def parse(self, request: ParseRequest) -> ParseResult:
        if not self.supports(request):
            return self._error("unsupported-type", "unsupported text/Markdown source")
        markdown = request.media_type == "text/markdown"
        if request.path is not None:
            markdown = request.path.suffix.lower() in {".md", ".markdown"}
            try:
                text = request.path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                return self._error("invalid-utf8", "source is not valid UTF-8")
            except OSError as exc:
                return self._error("read-error", f"unable to read source: {exc}")
        else:
            assert request.text is not None
            text = request.text

        content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        blocks: list[ParsedBlock] = []
        current_heading: str | None = None
        for line_number, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            kind = "paragraph"
            if markdown and stripped.startswith("#"):
                marker, separator, title = stripped.partition(" ")
                if separator and marker and set(marker) == {"#"} and len(marker) <= 6:
                    current_heading = title.strip()
                    kind = "heading"
            blocks.append(
                ParsedBlock(
                    ordinal=len(blocks),
                    text=line,
                    location=f"line:{line_number}",
                    heading=current_heading,
                    metadata={"kind": kind},
                )
            )
        return ParseResult(
            self.parser_id,
            self.parser_version,
            tuple(blocks),
            metadata={"content_hash": content_hash, "format": "markdown" if markdown else "text"},
        )

    def _error(self, code: str, message: str) -> ParseResult:
        return ParseResult(
            self.parser_id,
            self.parser_version,
            (),
            diagnostics=(ParseDiagnostic(ParseSeverity.ERROR, code, message),),
        )


class DocxParser:
    """DOCX parser preserving paragraph order and heading context."""

    parser_id = "docx"
    parser_version = "1"
    _word_ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

    def supports(self, request: ParseRequest) -> bool:
        return request.path is not None and request.path.suffix.lower() == ".docx"

    def parse(self, request: ParseRequest) -> ParseResult:
        if not self.supports(request):
            return self._error("unsupported-type", "unsupported DOCX source")
        assert request.path is not None
        try:
            with zipfile.ZipFile(request.path) as archive:
                document = archive.read("word/document.xml")
        except (OSError, KeyError, zipfile.BadZipFile):
            return self._error("malformed-docx", "DOCX is unreadable or missing its document body")
        try:
            root = ElementTree.fromstring(document)
        except ElementTree.ParseError:
            return self._error("malformed-docx", "DOCX document XML is malformed")

        namespace = {"w": self._word_ns}
        blocks: list[ParsedBlock] = []
        current_heading: str | None = None
        for paragraph_index, paragraph in enumerate(root.findall(".//w:body/w:p", namespace), start=1):
            text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
            if not text:
                continue
            style_node = paragraph.find("./w:pPr/w:pStyle", namespace)
            style = None if style_node is None else style_node.get(f"{{{self._word_ns}}}val")
            is_heading = bool(style and style.lower().startswith("heading"))
            if is_heading:
                current_heading = text
            blocks.append(
                ParsedBlock(
                    ordinal=len(blocks),
                    text=text,
                    location=f"paragraph:{paragraph_index}",
                    heading=current_heading,
                    metadata={"kind": "heading" if is_heading else "paragraph", "style": style or ""},
                )
            )
        return ParseResult(
            self.parser_id,
            self.parser_version,
            tuple(blocks),
            metadata={"format": "docx"},
        )

    def _error(self, code: str, message: str) -> ParseResult:
        return ParseResult(
            self.parser_id,
            self.parser_version,
            (),
            diagnostics=(ParseDiagnostic(ParseSeverity.ERROR, code, message),),
        )
