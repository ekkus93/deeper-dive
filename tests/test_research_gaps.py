from __future__ import annotations

import json

from deeper_dive.llm import FakeLLMProvider
from deeper_dive.research_gaps import ResearchGapCategory, ResearchGapPlanner, ResearchGapStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def test_fake_llm_generates_persisted_inspectable_gaps_without_search(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s1", "p", "user", "text", "Study", "now"))
    corpus.create_chunk(SourceChunkRecord("c1", "s1", 0, "A 2018 study reports result X.", "h"))

    response = json.dumps(
        {
            "gaps": [
                {
                    "category": "recency",
                    "rationale": "The corpus evidence is from 2018; newer evidence may exist.",
                    "priority": 4,
                    "source_ids": ["s1"],
                    "chunk_ids": ["c1"],
                },
                {
                    "category": "disagreement",
                    "rationale": "The corpus contains only one side of the claim.",
                    "priority": 3,
                    "source_ids": ["s1"],
                    "chunk_ids": ["c1"],
                },
                {
                    "category": "missing_context",
                    "rationale": "Background context is absent.",
                    "priority": 2,
                    "source_ids": [],
                    "chunk_ids": [],
                },
                {
                    "category": "cited_but_missing",
                    "rationale": "A referenced underlying paper is not present.",
                    "priority": 5,
                    "source_ids": ["s1"],
                    "chunk_ids": ["c1"],
                },
            ]
        }
    )
    provider = FakeLLMProvider(response=response)
    planner = ResearchGapPlanner(database, provider)

    gaps = planner.analyze("p")
    assert {gap.category for gap in gaps} == {
        ResearchGapCategory.RECENCY,
        ResearchGapCategory.DISAGREEMENT,
        ResearchGapCategory.MISSING_CONTEXT,
        ResearchGapCategory.CITED_BUT_MISSING,
    }
    assert all(gap.project_id == "p" for gap in gaps)
    assert provider.requests
    assert "Do not search the web" in provider.requests[0].messages[0].content

    reopened = ResearchGapStore(Database(tmp_path / "project.db"))
    persisted = reopened.list_project("p")
    assert len(persisted) == 4
    recency = next(gap for gap in persisted if gap.category is ResearchGapCategory.RECENCY)
    assert recency.source_ids == ("s1",)
    assert recency.chunk_ids == ("c1",)


def test_summary_excludes_disabled_sources_and_unknown_links_are_dropped(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(
        SourceRecord("hidden", "p", "user", "text", "Hidden", "now", included=False)
    )
    provider = FakeLLMProvider(
        response=json.dumps(
            {
                "gaps": [
                    {
                        "category": "other",
                        "rationale": "Needs investigation.",
                        "priority": 1,
                        "source_ids": ["hidden", "missing"],
                        "chunk_ids": ["missing"],
                    }
                ]
            }
        )
    )
    planner = ResearchGapPlanner(database, provider)
    assert planner.summarize("p").sources == ()
    gap = planner.analyze("p")[0]
    assert gap.source_ids == ()
    assert gap.chunk_ids == ()
