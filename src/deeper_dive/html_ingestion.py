"""Local HTML and explicit user URL ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from deeper_dive.parsing import (
    ParseDiagnostic,
    ParseRequest,
    ParseResult,
    ParseSeverity,
    ParsedBlock,
)

DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_BYTES = 5 * 1024 * 1024


class _ReadableHtmlParser(HTMLParser):
    """Small deterministic HTML-to-text extractor that ignores non-content elements."""

    _ignored = {"script", "style", "noscript", "svg", "template"}
    _block = {
        "article",
        "aside",
        "blockquote",
        "div",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "li",
        "main",
        "nav",
        "p",
        "section",
        "td",
        "th",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignored_depth = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in self._ignored:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self._block:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self._block:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self._parts.append(data)

    def text(self) -> str:
        lines = (" ".join(part.split()) for part in "".join(self._parts).splitlines())
        return "\n".join(line for line in lines if line)


@dataclass(frozen=True, slots=True)
class HtmlUrlParser:
    """Parse local HTML and fetch URLs explicitly supplied by the user."""

    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    max_bytes: int = DEFAULT_MAX_BYTES
    parser_id: str = "html-url"
    parser_version: str = "1"

    def supports(self, request: ParseRequest) -> bool:
        return request.path is not None and request.path.suffix.lower() in {".html", ".htm"}

    def parse(self, request: ParseRequest) -> ParseResult:
        if not self.supports(request):
            return self._error("unsupported-type", "unsupported local HTML source")
        assert request.path is not None
        try:
            data = request.path.read_bytes()
        except OSError as exc:
            return self._error("read-error", f"unable to read HTML source: {exc}")
        if len(data) > self.max_bytes:
            return self._error("oversized-response", "HTML source exceeds configured size limit")
        return self._parse_bytes(data, metadata={"format": "html", "source_origin": "user"})

    def fetch_user_url(self, url: str) -> ParseResult:
        """Fetch an explicit user URL; this is not automated research-network access."""

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return self._error("invalid-url", "explicit source URL must use HTTP or HTTPS")
        request = Request(url, headers={"User-Agent": "DeeperDive/0.1"})
        retrieved_at = datetime.now(UTC).isoformat()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                content_type = response.headers.get_content_type()
                final_url = response.geturl()
                data = response.read(self.max_bytes + 1)
        except HTTPError as exc:
            return self._error("http-error", f"HTTP request failed with status {exc.code}")
        except (URLError, TimeoutError) as exc:
            return self._error("fetch-error", f"unable to retrieve URL: {exc}")
        if len(data) > self.max_bytes:
            return self._error("oversized-response", "URL response exceeds configured size limit")
        metadata = {
            "original_url": url,
            "final_url": final_url,
            "retrieved_at": retrieved_at,
            "source_origin": "user",
            "content_type": content_type,
        }
        if content_type in {"text/html", "application/xhtml+xml"}:
            metadata["format"] = "html"
            return self._parse_bytes(data, metadata=metadata)
        if content_type.startswith("text/"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                return self._error("invalid-utf8", "text URL response is not valid UTF-8")
            blocks = (
                (ParsedBlock(0, text, location=final_url, metadata={"kind": "text"}),)
                if text
                else ()
            )
            return ParseResult(
                self.parser_id,
                self.parser_version,
                blocks,
                metadata={
                    **metadata,
                    "format": "text",
                    "content_hash": hashlib.sha256(data).hexdigest(),
                },
            )
        return self._error(
            "unsupported-content-type", f"unsupported URL content type: {content_type}"
        )

    def _parse_bytes(self, data: bytes, *, metadata: dict[str, str]) -> ParseResult:
        try:
            html = data.decode("utf-8")
        except UnicodeDecodeError:
            return self._error("invalid-utf8", "HTML source is not valid UTF-8")
        extractor = _ReadableHtmlParser()
        extractor.feed(html)
        text = extractor.text()
        diagnostics = ()
        if not text:
            diagnostics = (
                ParseDiagnostic(
                    ParseSeverity.WARNING,
                    "no-readable-text",
                    "HTML contains no readable text",
                ),
            )
        blocks = (
            (
                ParsedBlock(
                    0,
                    text,
                    location=metadata.get("final_url"),
                    metadata={"kind": "document"},
                ),
            )
            if text
            else ()
        )
        return ParseResult(
            self.parser_id,
            self.parser_version,
            blocks,
            diagnostics,
            metadata={**metadata, "content_hash": hashlib.sha256(data).hexdigest()},
        )

    def _error(self, code: str, message: str) -> ParseResult:
        return ParseResult(
            self.parser_id,
            self.parser_version,
            (),
            diagnostics=(ParseDiagnostic(ParseSeverity.ERROR, code, message),),
        )
