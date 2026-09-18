"""Batch source import planning and duplicate detection."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from deeper_dive.html_ingestion import HtmlUrlParser
from deeper_dive.parsing import ParseRequest, SourceParser


class DuplicateDisposition(StrEnum):
    """Disposition assigned before an import mutates project state."""

    IMPORT = "import"
    DUPLICATE_CONTENT = "duplicate_content"
    DUPLICATE_URL = "duplicate_url"
    UNSUPPORTED = "unsupported"
    READ_ERROR = "read_error"


@dataclass(frozen=True, slots=True)
class ImportCandidate:
    """One candidate discovered from files, directories, or explicit URLs."""

    locator: str
    title: str
    source_type: str
    disposition: DuplicateDisposition
    content_hash: str | None = None
    canonical_url: str | None = None
    reason: str = ""

    @property
    def should_import(self) -> bool:
        return self.disposition is DuplicateDisposition.IMPORT


@dataclass(frozen=True, slots=True)
class BatchImportPlan:
    """Dry-run import plan; UI/service code can present duplicate choices before import."""

    candidates: tuple[ImportCandidate, ...]

    @property
    def importable(self) -> tuple[ImportCandidate, ...]:
        return tuple(candidate for candidate in self.candidates if candidate.should_import)

    @property
    def duplicates(self) -> tuple[ImportCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if candidate.disposition
            in {
                DuplicateDisposition.DUPLICATE_CONTENT,
                DuplicateDisposition.DUPLICATE_URL,
            }
        )


def plan_file_imports(
    inputs: list[Path],
    parsers: list[SourceParser],
    *,
    existing_content_hashes: set[str] | None = None,
) -> BatchImportPlan:
    """Plan imports for files and directories without silently duplicating active sources."""

    known_hashes = set() if existing_content_hashes is None else set(existing_content_hashes)
    seen_hashes: set[str] = set()
    candidates: list[ImportCandidate] = []
    for path in _expand_inputs(inputs):
        parser = _parser_for(path, parsers)
        if parser is None:
            candidates.append(
                ImportCandidate(
                    str(path),
                    path.name,
                    "file",
                    DuplicateDisposition.UNSUPPORTED,
                    reason="unsupported extension",
                )
            )
            continue
        try:
            content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            candidates.append(
                ImportCandidate(
                    str(path),
                    path.name,
                    "file",
                    DuplicateDisposition.READ_ERROR,
                    reason=str(exc),
                )
            )
            continue
        if content_hash in known_hashes or content_hash in seen_hashes:
            disposition = DuplicateDisposition.DUPLICATE_CONTENT
            reason = "duplicate content hash"
        else:
            disposition = DuplicateDisposition.IMPORT
            reason = ""
            seen_hashes.add(content_hash)
        candidates.append(
            ImportCandidate(
                str(path),
                path.name,
                parser.parser_id,
                disposition,
                content_hash=content_hash,
                reason=reason,
            )
        )
    return BatchImportPlan(tuple(candidates))


def plan_url_imports(
    urls: list[str],
    parser: HtmlUrlParser,
    *,
    existing_canonical_urls: set[str] | None = None,
) -> BatchImportPlan:
    """Plan explicit URL imports by canonical URL before network fetch/import."""

    known_urls = set() if existing_canonical_urls is None else set(existing_canonical_urls)
    seen_urls: set[str] = set()
    candidates: list[ImportCandidate] = []
    for url in urls:
        canonical = canonicalize_url(url)
        if canonical is None:
            candidates.append(
                ImportCandidate(
                    url,
                    url,
                    parser.parser_id,
                    DuplicateDisposition.UNSUPPORTED,
                    reason="invalid HTTP/HTTPS URL",
                )
            )
            continue
        if canonical in known_urls or canonical in seen_urls:
            disposition = DuplicateDisposition.DUPLICATE_URL
            reason = "duplicate canonical URL"
        else:
            disposition = DuplicateDisposition.IMPORT
            reason = ""
            seen_urls.add(canonical)
        candidates.append(
            ImportCandidate(
                url,
                canonical,
                parser.parser_id,
                disposition,
                canonical_url=canonical,
                reason=reason,
            )
        )
    return BatchImportPlan(tuple(candidates))


def canonicalize_url(url: str) -> str | None:
    """Normalize explicit source URLs enough to detect exact URL duplicates."""

    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower() if parsed.hostname else ""
    if not host:
        return None
    if parsed.port and not (
        (scheme == "http" and parsed.port == 80) or (scheme == "https" and parsed.port == 443)
    ):
        netloc = f"{host}:{parsed.port}"
    else:
        netloc = host
    path = parsed.path or "/"
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)))
    return urlunsplit((scheme, netloc, path, query, ""))


def _expand_inputs(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        if item.is_dir():
            paths.extend(path for path in sorted(item.rglob("*")) if path.is_file())
        else:
            paths.append(item)
    return paths


def _parser_for(path: Path, parsers: list[SourceParser]) -> SourceParser | None:
    request = ParseRequest(path=path)
    for parser in parsers:
        if parser.supports(request):
            return parser
    return None
