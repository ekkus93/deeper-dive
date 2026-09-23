"""Deterministic supplemental research execution."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.research_candidates import CandidateEvaluator, CandidateOutcome
from deeper_dive.research_gaps import ResearchGap, ResearchGapStore
from deeper_dive.research_policy import ResearchPolicyStore
from deeper_dive.search import (
    FakeSearchProvider,
    FetchedDocument,
    FetchRequest,
    ResearchSearchService,
    SearchQuery,
    SearchResult,
)
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import CorpusRepository


class DeterministicSupplementalFetcher:
    """Offline fetcher for deterministic research execution."""

    def __init__(self, gap: ResearchGap, corpus: CorpusRepository) -> None:
        self.gap = gap
        self.corpus = corpus
        self.requests: list[FetchRequest] = []

    def fetch(self, request: FetchRequest) -> FetchedDocument:
        self.requests.append(request)
        wanted_chunks = set(self.gap.chunk_ids)
        excerpts: list[str] = []
        for source_id in self.gap.source_ids:
            for chunk in self.corpus.list_chunks(source_id):
                if chunk.id in wanted_chunks:
                    excerpts.append(chunk.text)
        excerpts_text = "\n".join(excerpts) if excerpts else "No corpus excerpts were attached."
        text = "\n".join(
            (
                f"Supplemental research candidate for gap {self.gap.id}.",
                f"Gap rationale: {self.gap.rationale}",
                "Corpus excerpts:",
                excerpts_text,
            )
        )
        return FetchedDocument(
            requested_url=request.url,
            final_url=request.url,
            text=text,
            content_type="text/plain",
            title=f"Supplemental candidate for {self.gap.id}",
        )


def execute_research_gaps(
    service: DeeperDiveService,
    project_id: str,
    gap_ids: tuple[str, ...],
) -> tuple[CandidateOutcome, ...]:
    """Research selected gaps without live network access."""

    if not gap_ids:
        raise ValueError("at least one research gap is required")
    database = Database(_project_database(service, project_id))
    policy = ResearchPolicyStore(database).project(project_id)
    if not policy.automated_search_allowed:
        raise ValueError("supplemental research is disabled by project policy")
    store = ResearchGapStore(database)
    gaps = {gap.id: gap for gap in store.list_project(project_id)}
    corpus = CorpusRepository(database)
    evaluator = CandidateEvaluator(database)
    sources = corpus.list_sources(project_id)
    known_urls = {source.locator for source in sources if source.locator}
    known_hashes = {source.content_hash for source in sources if source.content_hash}
    outcomes: list[CandidateOutcome] = []
    for gap_id in gap_ids:
        gap = gaps.get(gap_id)
        if gap is None or gap.project_id != project_id:
            raise KeyError(gap_id)
        if gap.status == "ignored":
            continue
        query = SearchQuery(
            text=gap.rationale,
            purpose="find supplemental source candidates for a persisted research gap",
            research_gap_id=gap.id,
            max_results=1,
        )
        result = _search_result_for_gap(project_id, gap, policy.mode.value)
        provider = FakeSearchProvider((result,))
        result = ResearchSearchService(provider).search(query)[0]
        fetcher = DeterministicSupplementalFetcher(gap, corpus)
        document = fetcher.fetch(FetchRequest(result.url))
        outcome = evaluator.evaluate(
            gap,
            result,
            document,
            existing_urls=set(known_urls),
            existing_hashes=set(known_hashes),
        )
        outcomes.append(outcome)
        known_urls.add(outcome.url)
        known_hashes.add(outcome.content_hash)
        if outcome.accepted:
            service.add_pasted_source(
                project_id,
                document.title or result.title,
                document.text,
                origin="supplemental",
            )
    return tuple(outcomes)


def _project_database(service: DeeperDiveService, project_id: str) -> Path:
    return service.workspaces.project_root(project_id) / "project.db"


def _search_result_for_gap(project_id: str, gap: ResearchGap, mode: str) -> SearchResult:
    return SearchResult(
        url=_candidate_url(project_id, gap),
        title=f"Supplemental candidate for {gap.category.value}",
        snippet=gap.rationale,
        rank=1,
        provider_metadata=(("mode", mode),),
    )


def _candidate_url(project_id: str, gap: ResearchGap) -> str:
    quoted_identity = quote(f"{project_id}/{gap.id}", safe="/")
    return f"deeper-dive://supplemental-research/{quoted_identity}"
