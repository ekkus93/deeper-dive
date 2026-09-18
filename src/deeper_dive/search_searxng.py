"""SearXNG JSON search adapter for supplemental research."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from deeper_dive.search import SearchQuery, SearchResult


class SearchProviderError(RuntimeError):
    pass


@dataclass(slots=True)
class SearxngSearchProvider:
    """Search a configured SearXNG instance through its public JSON API."""

    base_url: str
    timeout_seconds: float = 10.0
    max_results: int = 20

    @property
    def provider_id(self) -> str:
        return "searxng"

    def search(self, query: SearchQuery) -> tuple[SearchResult, ...]:
        query.validate_automated()
        limit = min(query.max_results, self.max_results)
        params = urlencode({"q": query.text, "format": "json"})
        request = Request(
            f"{self.base_url.rstrip('/')}/search?{params}",
            headers={"Accept": "application/json", "User-Agent": "deeper-dive/0.1"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429:
                raise SearchProviderError("SearXNG rate limit exceeded") from exc
            raise SearchProviderError(f"SearXNG HTTP error {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SearchProviderError(f"SearXNG search failed: {type(exc).__name__}") from exc
        raw_results = payload.get("results", [])
        if not isinstance(raw_results, list):
            raise SearchProviderError("SearXNG returned malformed results")
        results: list[SearchResult] = []
        for item in raw_results[:limit]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url", "")).strip()
            title = str(item.get("title", "")).strip()
            if not url or not title:
                continue
            engines = item.get("engines", [])
            metadata = (("engines", ",".join(str(value) for value in engines)),)
            results.append(
                SearchResult(
                    url=url,
                    title=title,
                    snippet=str(item.get("content", "")),
                    rank=len(results) + 1,
                    provider_metadata=metadata,
                )
            )
        return tuple(results)
