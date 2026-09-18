"""Corpus analysis and persisted supplemental-research gap planning."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from deeper_dive.llm import LLMMessage, LLMProvider, LLMRequest
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import CorpusRepository


class ResearchGapCategory(StrEnum):
    MISSING_CONTEXT = "missing_context"
    DISAGREEMENT = "disagreement"
    RECENCY = "recency"
    CITED_BUT_MISSING = "cited_but_missing"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class CorpusSourceSummary:
    source_id: str
    title: str
    origin: str
    chunk_ids: tuple[str, ...]
    excerpt: str


@dataclass(frozen=True, slots=True)
class CorpusSummary:
    project_id: str
    sources: tuple[CorpusSourceSummary, ...]


@dataclass(frozen=True, slots=True)
class ResearchGap:
    id: str
    project_id: str
    category: ResearchGapCategory
    rationale: str
    priority: int
    source_ids: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...] = ()
    status: str = "open"


class ResearchGapStore:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def replace_project(self, project_id: str, gaps: tuple[ResearchGap, ...]) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM research_gaps WHERE project_id=?", (project_id,))
            for gap in gaps:
                db.execute(
                    """INSERT INTO research_gaps
                    (id,project_id,category,rationale,priority,source_ids_json,chunk_ids_json,status)
                    VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        gap.id,
                        project_id,
                        gap.category.value,
                        gap.rationale,
                        gap.priority,
                        json.dumps(gap.source_ids),
                        json.dumps(gap.chunk_ids),
                        gap.status,
                    ),
                )

    def list_project(self, project_id: str) -> tuple[ResearchGap, ...]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM research_gaps WHERE project_id=? ORDER BY priority DESC,id",
                (project_id,),
            ).fetchall()
        return tuple(
            ResearchGap(
                id=str(row["id"]),
                project_id=str(row["project_id"]),
                category=ResearchGapCategory(str(row["category"])),
                rationale=str(row["rationale"]),
                priority=int(row["priority"]),
                source_ids=tuple(json.loads(str(row["source_ids_json"]))),
                chunk_ids=tuple(json.loads(str(row["chunk_ids_json"]))),
                status=str(row["status"]),
            )
            for row in rows
        )

    def _ensure_schema(self) -> None:
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS research_gaps (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    source_ids_json TEXT NOT NULL,
                    chunk_ids_json TEXT NOT NULL,
                    status TEXT NOT NULL
                )"""
            )


class ResearchGapPlanner:
    """Analyze an existing corpus without performing any web search."""

    def __init__(self, database: Database, provider: LLMProvider) -> None:
        self.database = database
        self.provider = provider
        self.corpus = CorpusRepository(database)
        self.store = ResearchGapStore(database)

    def summarize(self, project_id: str) -> CorpusSummary:
        summaries: list[CorpusSourceSummary] = []
        for source in self.corpus.list_sources(project_id):
            if not source.included:
                continue
            chunks = self.corpus.list_chunks(source.id)
            excerpt = "\n".join(chunk.text for chunk in chunks)[:4000]
            summaries.append(
                CorpusSourceSummary(
                    source.id,
                    source.title,
                    source.origin,
                    tuple(chunk.id for chunk in chunks),
                    excerpt,
                )
            )
        return CorpusSummary(project_id, tuple(summaries))

    def analyze(self, project_id: str, *, model: str | None = None) -> tuple[ResearchGap, ...]:
        summary = self.summarize(project_id)
        payload = {
            "project_id": project_id,
            "sources": [
                {
                    "source_id": source.source_id,
                    "title": source.title,
                    "origin": source.origin,
                    "chunk_ids": source.chunk_ids,
                    "excerpt": source.excerpt,
                }
                for source in summary.sources
            ],
        }
        request = LLMRequest(
            messages=(
                LLMMessage(
                    "system",
                    "Identify research gaps only. Do not search the web. "
                    "Return JSON with a gaps array. Categories: missing_context, disagreement, "
                    "recency, cited_but_missing, other. Each gap needs category, rationale, "
                    "priority 1-5, source_ids, and chunk_ids.",
                ),
                LLMMessage("user", json.dumps(payload, sort_keys=True)),
            ),
            model=model,
        )
        response = self.provider.generate(request)
        raw = response.structured if response.structured is not None else json.loads(response.text)
        items = raw.get("gaps", [])
        if not isinstance(items, list):
            raise ValueError("research gap response must contain a gaps array")
        known_sources = {source.source_id for source in summary.sources}
        known_chunks = {chunk_id for source in summary.sources for chunk_id in source.chunk_ids}
        gaps: list[ResearchGap] = []
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("research gap entries must be objects")
            category = ResearchGapCategory(str(item.get("category", "other")))
            rationale = str(item.get("rationale", "")).strip()
            priority = int(item.get("priority", 3))
            if not rationale or not 1 <= priority <= 5:
                raise ValueError("research gaps require rationale and priority from 1 through 5")
            source_ids = tuple(
                str(value) for value in item.get("source_ids", []) if str(value) in known_sources
            )
            chunk_ids = tuple(
                str(value) for value in item.get("chunk_ids", []) if str(value) in known_chunks
            )
            gaps.append(
                ResearchGap(
                    str(uuid4()), project_id, category, rationale, priority, source_ids, chunk_ids
                )
            )
        result = tuple(gaps)
        self.store.replace_project(project_id, result)
        return result
