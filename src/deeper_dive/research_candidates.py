"""Evaluation, deduplication, and history for supplemental research candidates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import uuid4

from deeper_dive.research_gaps import ResearchGap
from deeper_dive.search import FetchedDocument, SearchResult
from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class CandidateOutcome:
    id: str
    project_id: str
    gap_id: str
    url: str
    title: str
    accepted: bool
    reason: str
    authority_score: int
    content_hash: str
    origin: str = "supplemental"


class CandidateEvaluator:
    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def evaluate(
        self,
        gap: ResearchGap,
        result: SearchResult,
        document: FetchedDocument,
        *,
        existing_urls: set[str] | None = None,
        existing_hashes: set[str] | None = None,
    ) -> CandidateOutcome:
        content_hash = hashlib.sha256(document.text.encode()).hexdigest()
        known_urls = existing_urls or set()
        known_hashes = existing_hashes or set()
        if document.final_url in known_urls or result.url in known_urls:
            accepted, reason = False, "duplicate URL"
        elif content_hash in known_hashes:
            accepted, reason = False, "duplicate content"
        else:
            gap_terms = self._terms(gap.rationale)
            candidate_terms = self._terms(f"{result.title} {result.snippet} {document.text[:4000]}")
            overlap = gap_terms & candidate_terms
            if gap_terms and not overlap:
                accepted, reason = False, "candidate is not relevant to the motivating gap"
            else:
                accepted = True
                reason = f"accepted for gap {gap.id}: {gap.rationale}"
        outcome = CandidateOutcome(
            str(uuid4()),
            gap.project_id,
            gap.id,
            document.final_url,
            result.title,
            accepted,
            reason,
            self._authority(document.final_url),
            content_hash,
        )
        self._persist(outcome)
        return outcome

    def list_project(self, project_id: str) -> tuple[CandidateOutcome, ...]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM research_candidate_outcomes WHERE project_id=? ORDER BY id",
                (project_id,),
            ).fetchall()
        return tuple(
            CandidateOutcome(
                id=str(row["id"]),
                project_id=str(row["project_id"]),
                gap_id=str(row["gap_id"]),
                url=str(row["url"]),
                title=str(row["title"]),
                accepted=bool(row["accepted"]),
                reason=str(row["reason"]),
                authority_score=int(row["authority_score"]),
                content_hash=str(row["content_hash"]),
                origin="supplemental",
            )
            for row in rows
        )

    @staticmethod
    def _terms(text: str) -> set[str]:
        return {word.strip(".,:;!?()[]{}\"'").lower() for word in text.split() if len(word) > 3}

    @staticmethod
    def _authority(url: str) -> int:
        host = (urlsplit(url).hostname or "").lower()
        if host.endswith(".gov") or host.endswith(".edu"):
            return 3
        if host.endswith(".org"):
            return 2
        return 1

    def _persist(self, outcome: CandidateOutcome) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO research_candidate_outcomes
                (id,project_id,gap_id,url,title,accepted,reason,authority_score,content_hash)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    outcome.id,
                    outcome.project_id,
                    outcome.gap_id,
                    outcome.url,
                    outcome.title,
                    int(outcome.accepted),
                    outcome.reason,
                    outcome.authority_score,
                    outcome.content_hash,
                ),
            )

    def _ensure_schema(self) -> None:
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS research_candidate_outcomes (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    gap_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    authority_score INTEGER NOT NULL,
                    content_hash TEXT NOT NULL
                )"""
            )
