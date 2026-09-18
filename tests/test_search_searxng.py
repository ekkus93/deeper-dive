from __future__ import annotations

import io
import json
from urllib.error import HTTPError

import pytest

from deeper_dive.search import ResearchSearchService, SearchQuery
from deeper_dive.search_searxng import SearchProviderError, SearxngSearchProvider


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode()

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_searxng_normalizes_and_bounds_results(monkeypatch) -> None:
    payload = {
        "results": [
            {"url": "https://a.test", "title": "A", "content": "one", "engines": ["x"]},
            {"url": "https://b.test", "title": "B", "content": "two", "engines": ["y"]},
        ]
    }
    monkeypatch.setattr("deeper_dive.search_searxng.urlopen", lambda request, timeout: FakeResponse(payload))
    provider = SearxngSearchProvider("https://search.example", max_results=1)
    results = ResearchSearchService(provider).search(
        SearchQuery("topic", "fill gap", research_gap_id="gap-1", max_results=10)
    )
    assert len(results) == 1
    assert results[0].url == "https://a.test"
    assert results[0].rank == 1
    assert results[0].provider_metadata == (("engines", "x"),)


def test_searxng_rate_limit_is_actionable(monkeypatch) -> None:
    def fail(request: object, timeout: float) -> FakeResponse:
        raise HTTPError("https://search.example", 429, "rate", {}, io.BytesIO())

    monkeypatch.setattr("deeper_dive.search_searxng.urlopen", fail)
    provider = SearxngSearchProvider("https://search.example")
    with pytest.raises(SearchProviderError, match="rate limit"):
        provider.search(SearchQuery("topic", "fill gap", research_gap_id="gap-1"))
