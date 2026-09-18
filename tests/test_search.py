from __future__ import annotations

import pytest

from deeper_dive.search import FakeSearchProvider, ResearchSearchService, SearchQuery, SearchResult


def test_fake_search_is_deterministic_and_bounded() -> None:
    provider = FakeSearchProvider(
        (
            SearchResult("https://example.test/a", "A", rank=1),
            SearchResult("https://example.test/b", "B", rank=2),
        )
    )
    service = ResearchSearchService(provider)
    query = SearchQuery("new evidence", "resolve recency gap", research_gap_id="gap-1", max_results=1)
    assert service.search(query) == (SearchResult("https://example.test/a", "A", rank=1),)
    assert provider.queries == [query]


def test_automated_search_requires_gap_or_question_and_purpose() -> None:
    provider = FakeSearchProvider()
    service = ResearchSearchService(provider)
    with pytest.raises(ValueError, match="research gap or research question ID"):
        service.search(SearchQuery("topic", "find context"))
    with pytest.raises(ValueError, match="query purpose"):
        service.search(SearchQuery("topic", "", research_gap_id="gap-1"))
    assert provider.queries == []


def test_research_question_is_valid_association() -> None:
    provider = FakeSearchProvider()
    service = ResearchSearchService(provider)
    query = SearchQuery("topic", "answer question", research_question_id="question-1")
    assert service.search(query) == ()
    assert provider.queries == [query]
