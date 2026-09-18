from __future__ import annotations

import socket

import pytest

from deeper_dive.research_fetch import ResearchFetchError, ResearchSafeFetcher, TransportResponse
from deeper_dive.search import FetchRequest


class FakeTransport:
    def __init__(self, responses: list[TransportResponse | Exception]) -> None:
        self.responses = responses
        self.urls: list[str] = []

    def get(self, url: str, timeout_seconds: float, max_bytes: int) -> TransportResponse:
        self.urls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def resolver_for(address: str):
    def resolve(host: str, port: int, *, type: int):
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port))]

    return resolve


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1", "fc00::1"])
def test_rejects_non_public_addresses(address: str) -> None:
    fetcher = ResearchSafeFetcher(transport=FakeTransport([]), resolver=resolver_for(address))
    with pytest.raises(ResearchFetchError, match="non-public"):
        fetcher.fetch(FetchRequest("https://example.test"))


def test_redirect_is_revalidated_and_private_target_rejected() -> None:
    transport = FakeTransport([TransportResponse(302, {"location": "http://127.0.0.1/x"}, b"")])

    def resolve(host: str, port: int, *, type: int):
        address = "93.184.216.34" if host == "example.test" else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    fetcher = ResearchSafeFetcher(transport=transport, resolver=resolve)
    with pytest.raises(ResearchFetchError, match="non-public"):
        fetcher.fetch(FetchRequest("https://example.test"))
    assert transport.urls == ["https://example.test"]


def test_oversized_body_is_rejected() -> None:
    transport = FakeTransport([TransportResponse(200, {"content-type": "text/plain"}, b"12345")])
    fetcher = ResearchSafeFetcher(transport=transport, resolver=resolver_for("93.184.216.34"))
    with pytest.raises(ResearchFetchError, match="maximum size"):
        fetcher.fetch(FetchRequest("https://example.test", max_bytes=4))


def test_timeout_is_clean_error() -> None:
    class TimeoutTransport:
        def get(self, url: str, timeout_seconds: float, max_bytes: int) -> TransportResponse:
            raise ResearchFetchError("fetch failed: TimeoutError")

    fetcher = ResearchSafeFetcher(transport=TimeoutTransport(), resolver=resolver_for("93.184.216.34"))
    with pytest.raises(ResearchFetchError, match="TimeoutError"):
        fetcher.fetch(FetchRequest("https://example.test"))


def test_invalid_scheme_and_content_type_are_rejected() -> None:
    fetcher = ResearchSafeFetcher(transport=FakeTransport([]), resolver=resolver_for("93.184.216.34"))
    with pytest.raises(ResearchFetchError, match="HTTP/HTTPS"):
        fetcher.fetch(FetchRequest("file:///etc/passwd"))

    transport = FakeTransport([TransportResponse(200, {"content-type": "application/pdf"}, b"pdf")])
    fetcher = ResearchSafeFetcher(transport=transport, resolver=resolver_for("93.184.216.34"))
    with pytest.raises(ResearchFetchError, match="content type"):
        fetcher.fetch(FetchRequest("https://example.test"))


def test_html_is_extracted_and_canonical_redirect_url_retained() -> None:
    transport = FakeTransport(
        [
            TransportResponse(301, {"location": "/final"}, b""),
            TransportResponse(200, {"content-type": "text/html; charset=utf-8"}, b"<h1>Title</h1><p>Body</p>"),
        ]
    )
    fetcher = ResearchSafeFetcher(transport=transport, resolver=resolver_for("93.184.216.34"))
    document = fetcher.fetch(FetchRequest("https://example.test/start"))
    assert document.final_url == "https://example.test/final"
    assert document.text == "Title\nBody"
