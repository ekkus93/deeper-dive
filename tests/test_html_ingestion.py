from __future__ import annotations

from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import deeper_dive.html_ingestion as module
from deeper_dive.html_ingestion import HtmlUrlParser
from deeper_dive.parsing import ParseRequest


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        content_type: str = "text/html",
        final_url: str = "https://example.test/final",
    ) -> None:
        self._body = BytesIO(body)
        self._final_url = final_url
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def geturl(self) -> str:
        return self._final_url


def test_local_html_extracts_readable_text(tmp_path: Path) -> None:
    path = tmp_path / "source.html"
    path.write_text(
        "<html><main><h1>Title</h1><p>Hello <b>world</b>.</p>"
        "<script>ignore()</script></main></html>"
    )
    result = HtmlUrlParser().parse(ParseRequest(path=path))
    assert not result.has_errors
    assert result.blocks[0].text == "Title\nHello world."
    assert result.metadata["source_origin"] == "user"


def test_explicit_url_preserves_origin_redirect_and_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = FakeResponse(b"<main><p>Useful article</p></main>")
    monkeypatch.setattr(module, "urlopen", lambda request, timeout: response)
    result = HtmlUrlParser().fetch_user_url("https://example.test/original")
    assert result.blocks[0].text == "Useful article"
    assert result.metadata["original_url"] == "https://example.test/original"
    assert result.metadata["final_url"] == "https://example.test/final"
    assert result.metadata["source_origin"] == "user"
    assert result.metadata["retrieved_at"]


def test_non_html_text_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "urlopen",
        lambda request, timeout: FakeResponse(b"plain text", "text/plain"),
    )
    result = HtmlUrlParser().fetch_user_url("https://example.test/plain")
    assert result.blocks[0].text == "plain text"
    assert result.metadata["format"] == "text"


def test_oversized_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "urlopen", lambda request, timeout: FakeResponse(b"12345"))
    result = HtmlUrlParser(max_bytes=4).fetch_user_url("https://example.test/large")
    assert result.has_errors
    assert result.diagnostics[0].code == "oversized-response"


def test_timeout_or_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(request: object, timeout: float) -> FakeResponse:
        raise URLError("timed out")

    monkeypatch.setattr(module, "urlopen", fail)
    result = HtmlUrlParser().fetch_user_url("https://example.test/slow")
    assert result.has_errors
    assert result.diagnostics[0].code == "fetch-error"


def test_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(request: object, timeout: float) -> FakeResponse:
        raise HTTPError("https://example.test/missing", 404, "missing", {}, None)

    monkeypatch.setattr(module, "urlopen", fail)
    result = HtmlUrlParser().fetch_user_url("https://example.test/missing")
    assert result.has_errors
    assert result.diagnostics[0].code == "http-error"


def test_rejects_non_http_url() -> None:
    result = HtmlUrlParser().fetch_user_url("file:///etc/passwd")
    assert result.has_errors
    assert result.diagnostics[0].code == "invalid-url"
