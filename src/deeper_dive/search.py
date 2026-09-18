"""Provider-neutral search and fetch contracts for supplemental research."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SearchQuery:
    text: str
    purpose: str
    research_gap_id: str | None = None
    research_question_id: str | None = None
    max_results: int = 10

    def validate_automated(self) -> None:
        if not self.text.strip():
            raise ValueError("search query text must not be empty")
        if not self.purpose.strip():
            raise ValueError("automated search requires a query purpose")
        if not self.research_gap_id and not self.research_question_id:
            raise ValueError("automated search requires a research gap or research question ID")
        if not 1 <= self.max_results <= 100:
            raise ValueError("max_results must be between 1 and 100")


@dataclass(frozen=True, slots=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""
    rank: int = 0
    provider_metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FetchRequest:
    url: str
    timeout_seconds: float = 15.0
    max_bytes: int = 2_000_000


@dataclass(frozen=True, slots=True)
class FetchedDocument:
    requested_url: str
    final_url: str
    text: str
    content_type: str
    title: str = ""


class SearchProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def search(self, query: SearchQuery) -> tuple[SearchResult, ...]: ...


class DocumentFetcher(Protocol):
    def fetch(self, request: FetchRequest) -> FetchedDocument: ...


class FakeSearchProvider:
    """Deterministic model-free search provider for tests and orchestration."""

    def __init__(self, results: tuple[SearchResult, ...] = ()) -> None:
        self.results = results
        self.queries: list[SearchQuery] = []

    @property
    def provider_id(self) -> str:
        return "fake"

    def search(self, query: SearchQuery) -> tuple[SearchResult, ...]:
        self.queries.append(query)
        return self.results[: query.max_results]


class ResearchSearchService:
    """Mandatory policy boundary for automated research search calls."""

    def __init__(self, provider: SearchProvider) -> None:
        self.provider = provider

    def search(self, query: SearchQuery) -> tuple[SearchResult, ...]:
        query.validate_automated()
        return self.provider.search(query)
