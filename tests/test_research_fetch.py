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


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.1.1",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_rejects_non_public_addresses(address: str) -> None:
    fetcher = ResearchSafeFetcher(
        transport=FakeTransport([]),
        resolver=resolver_for(address),
    )
    with pytest.raises(ResearchFetchError, match="non-public"):
        fetcher.fetch(FetchRequest("https://example.test"))


def test_rejects_dns_answer_set_containing_private_address() -> None:
    def resolve(host: str, port: int, *, type: int):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    fetcher = ResearchSafeFetcher(transport=FakeTransport([]), resolver=resolve)
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


def test_multi_hop_redirect_chain_revalidates_every_target() -> None:
    transport = FakeTransport(
        [
            TransportResponse(302, {"location": "https://second.test/step"}, b""),
            TransportResponse(307, {"location": "http://[::1]/private"}, b""),
        ]
    )

    def resolve(host: str, port: int, *, type: int):
        address = "93.184.216.34" if host in {"first.test", "second.test"} else "::1"
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (address, port))]

    fetcher = ResearchSafeFetcher(transport=transport, resolver=resolve)
    with pytest.raises(ResearchFetchError, match="non-public"):
        fetcher.fetch(FetchRequest("https://first.test/start"))
    assert transport.urls == ["https://first.test/start", "https://second.test/step"]


def test_redirect_limit_is_bounded() -> None:
    transport = FakeTransport(
        [TransportResponse(302, {"location": f"/hop-{index}"}, b"") for index in range(3)]
    )
    fetcher = ResearchSafeFetcher(
        transport=transport,
        resolver=resolver_for("93.184.216.34"),
        max_redirects=2,
    )
    with pytest.raises(ResearchFetchError, match="too many redirects"):
        fetcher.fetch(FetchRequest("https://example.test/start"))
    assert len(transport.urls) == 3


def test_oversized_body_is_rejected() -> None:
    transport = FakeTransport([TransportResponse(200, {"content-type": "text/plain"}, b"12345")])
    fetcher = ResearchSafeFetcher(
        transport=transport,
        resolver=resolver_for("93.184.216.34"),
    )
    with pytest.raises(ResearchFetchError, match="maximum size"):
        fetcher.fetch(FetchRequest("https://example.test", max_bytes=4))


def test_timeout_is_clean_error() -> None:
    class TimeoutTransport:
        def get(self, url: str, timeout_seconds: float, max_bytes: int) -> TransportResponse:
            raise ResearchFetchError("fetch failed: TimeoutError")

    fetcher = ResearchSafeFetcher(
        transport=TimeoutTransport(),
        resolver=resolver_for("93.184.216.34"),
    )
    with pytest.raises(ResearchFetchError, match="TimeoutError"):
        fetcher.fetch(FetchRequest("https://example.test"))


def test_invalid_scheme_and_content_type_are_rejected() -> None:
    fetcher = ResearchSafeFetcher(
        transport=FakeTransport([]),
        resolver=resolver_for("93.184.216.34"),
    )
    with pytest.raises(ResearchFetchError, match="HTTP/HTTPS"):
        fetcher.fetch(FetchRequest("file:///etc/passwd"))

    transport = FakeTransport([TransportResponse(200, {"content-type": "application/pdf"}, b"pdf")])
    fetcher = ResearchSafeFetcher(
        transport=transport,
        resolver=resolver_for("93.184.216.34"),
    )
    with pytest.raises(ResearchFetchError, match="content type"):
        fetcher.fetch(FetchRequest("https://example.test"))


def test_html_is_extracted_and_canonical_redirect_url_retained() -> None:
    transport = FakeTransport(
        [
            TransportResponse(301, {"location": "/final"}, b""),
            TransportResponse(
                200,
                {"content-type": "text/html; charset=utf-8"},
                b"<h1>Title</h1><p>Body</p>",
            ),
        ]
    )
    fetcher = ResearchSafeFetcher(
        transport=transport,
        resolver=resolver_for("93.184.216.34"),
    )
    document = fetcher.fetch(FetchRequest("https://example.test/start"))
    assert document.final_url == "https://example.test/final"
    assert document.text == "Title\nBody"
