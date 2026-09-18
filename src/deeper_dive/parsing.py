"""Normalized parser contracts for source ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol


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
