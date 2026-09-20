# fmt: off
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from deeper_dive.deterministic_fixture import DeterministicFixtureRunner
from deeper_dive.research_candidates import CandidateEvaluator
from deeper_dive.research_gaps import ResearchGap, ResearchGapCategory
from deeper_dive.research_policy import ResearchMode, ResearchPolicy
from deeper_dive.search import (
    FakeSearchProvider,
    FetchedDocument,
    ResearchSearchService,
    SearchQuery,
    SearchResult,
)
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def test_research_modes_and_off_search_gate() -> None:
    provider = FakeSearchProvider()
    service = ResearchSearchService(provider)
    modes = (ResearchMode.CONSERVATIVE, ResearchMode.USEFUL, ResearchMode.AGGRESSIVE)
    for mode in modes:
        policy = ResearchPolicy(mode)
        assert policy.automated_search_allowed
        query = SearchQuery(mode.value, "gap path", research_gap_id=f"gap-{mode.value}")
        service.search(query)
    assert len(provider.queries) == 3
    assert not ResearchPolicy(ResearchMode.OFF).automated_search_allowed


def test_recency_contradiction_and_missing_citation_gap_categories() -> None:
    categories = {
        ResearchGapCategory.RECENCY,
        ResearchGapCategory.DISAGREEMENT,
        ResearchGapCategory.CITED_BUT_MISSING,
    }
    values = {item.value for item in categories}
    assert values == {"recency", "disagreement", "cited_but_missing"}


def test_candidate_duplicate_and_weak_rejection_matrix(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    evaluator = CandidateEvaluator(database)
    gap = ResearchGap("g", "p", ResearchGapCategory.RECENCY, "newer climate evidence", 4)
    result = SearchResult("https://agency.gov/new", "New climate evidence", "climate evidence")
    document = FetchedDocument(result.url, result.url, "newer climate evidence", "text/plain")
    accepted = evaluator.evaluate(gap, result, document)
    assert accepted.accepted
    digest = hashlib.sha256(document.text.encode()).hexdigest()
    duplicate = evaluator.evaluate(gap, result, document, existing_hashes={digest})
    assert not duplicate.accepted
    assert duplicate.reason == "duplicate content"
    weak_result = SearchResult("https://example.test/food", "Pasta", "cooking recipe")
    weak_doc = FetchedDocument(
        weak_result.url, weak_result.url, "tomato pasta recipe", "text/plain"
    )
    weak = evaluator.evaluate(gap, weak_result, weak_doc)
    assert not weak.accepted
    assert "not relevant" in weak.reason


def test_supplemental_provenance_reaches_final_manifest(tmp_path: Path) -> None:
    result = DeterministicFixtureRunner(WorkspaceManager(tmp_path)).run()
    manifest = json.loads(result.artifacts.manifest.read_text(encoding="utf-8"))
    sources = manifest["sources"]
    supplemental = [source for source in sources if source["origin"] == "supplemental"]
    assert supplemental
    assert supplemental[0]["locator"].startswith("fixture://supplemental/")
# fmt: on
