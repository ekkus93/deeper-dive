from __future__ import annotations

from deeper_dive.research_candidates import CandidateEvaluator
from deeper_dive.research_gaps import ResearchGap, ResearchGapCategory
from deeper_dive.search import FetchedDocument, SearchResult
from deeper_dive.storage.database import Database


def gap() -> ResearchGap:
    return ResearchGap(
        "gap-1",
        "p",
        ResearchGapCategory.RECENCY,
        "Need newer climate evidence",
        4,
    )


def test_acceptance_records_supplemental_origin_reason_metadata_and_history(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    evaluator = CandidateEvaluator(database)
    result = SearchResult("https://agency.gov/study", "New climate study", "newer climate evidence")
    document = FetchedDocument(
        result.url,
        result.url,
        "This newer climate evidence updates the prior study.",
        "text/html",
    )
    outcome = evaluator.evaluate(gap(), result, document)
    assert outcome.accepted
    assert outcome.origin == "supplemental"
    assert outcome.gap_id == "gap-1"
    assert "gap gap-1" in outcome.reason
    assert outcome.authority_score == 3
    assert evaluator.list_project("p") == (outcome,)


def test_duplicate_and_irrelevant_rejections_remain_inspectable(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    evaluator = CandidateEvaluator(database)
    result = SearchResult("https://example.org/a", "Cooking recipes", "pasta sauce")
    document = FetchedDocument(result.url, result.url, "pasta cooking recipes", "text/plain")
    irrelevant = evaluator.evaluate(gap(), result, document)
    assert not irrelevant.accepted
    assert "not relevant" in irrelevant.reason

    duplicate = evaluator.evaluate(gap(), result, document, existing_urls={result.url})
    assert not duplicate.accepted
    assert duplicate.reason == "duplicate URL"
    assert len(evaluator.list_project("p")) == 2
