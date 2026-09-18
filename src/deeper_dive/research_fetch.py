"""Network-hardened HTTP fetcher for automated supplemental research."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from deeper_dive.search import FetchRequest, FetchedDocument


class ResearchFetchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TransportResponse:
    status: int
    headers: dict[str, str]
    body: bytes


class FetchTransport(Protocol):
    def get(self, url: str, timeout_seconds: float, max_bytes: int) -> TransportResponse: ...


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class UrllibTransport:
    def get(self, url: str, timeout_seconds: float, max_bytes: int) -> TransportResponse:
        opener = build_opener(_NoRedirect())
        request = Request(url, headers={"User-Agent": "deeper-dive/0.1"})
        try:
            response = opener.open(request, timeout=timeout_seconds)
        except Exception as exc:
            if hasattr(exc, "code") and hasattr(exc, "headers"):
                response = exc
            else:
                raise ResearchFetchError(f"fetch failed: {type(exc).__name__}") from exc
        try:
            body = response.read(max_bytes + 1)
            headers = {key.lower(): value for key, value in response.headers.items()}
            return TransportResponse(int(response.code), headers, body)
        finally:
            response.close()


class ResearchSafeFetcher:
    def __init__(
        self,
        *,
        transport: FetchTransport | None = None,
        resolver=socket.getaddrinfo,
        max_redirects: int = 5,
    ) -> None:
        self.transport = transport or UrllibTransport()
        self.resolver = resolver
        self.max_redirects = max_redirects

    def fetch(self, request: FetchRequest) -> FetchedDocument:
        current = request.url
        for _ in range(self.max_redirects + 1):
            self._validate_public_http_url(current)
            response = self.transport.get(current, request.timeout_seconds, request.max_bytes)
            if len(response.body) > request.max_bytes:
                raise ResearchFetchError("response exceeds maximum size")
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ResearchFetchError("redirect response is missing Location")
                current = urljoin(current, location)
                continue
            if not 200 <= response.status < 300:
                raise ResearchFetchError(f"HTTP error {response.status}")
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type not in {"text/html", "text/plain"}:
                raise ResearchFetchError(f"unsupported content type: {content_type or 'missing'}")
            charset = "utf-8"
            text = response.body.decode(charset, errors="replace")
            if content_type == "text/html":
                text = self._html_to_text(text)
            return FetchedDocument(request.url, current, text, content_type)
        raise ResearchFetchError("too many redirects")

    def _validate_public_http_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise ResearchFetchError("automated research permits HTTP/HTTPS URLs only")
        if not parsed.hostname:
            raise ResearchFetchError("URL requires a hostname")
        try:
            records = self.resolver(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ResearchFetchError("DNS resolution failed") from exc
        if not records:
            raise ResearchFetchError("DNS resolution returned no addresses")
        for record in records:
            address = ipaddress.ip_address(record[4][0])
            if not address.is_global:
                raise ResearchFetchError(f"automated research rejects non-public address {address}")

    @staticmethod
    def _html_to_text(html: str) -> str:
        from html.parser import HTMLParser

        class TextParser(HTMLParser):
            def __init__(self) -> None:
                super().__init__()
                self.parts: list[str] = []

            def handle_data(self, data: str) -> None:
                value = data.strip()
                if value:
                    self.parts.append(value)

        parser = TextParser()
        parser.feed(html)
        return "\n".join(parser.parts)
