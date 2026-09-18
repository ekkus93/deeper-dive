"""Claim evidence retrieval with source provenance and support/counterevidence coexistence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from deeper_dive.material_claims import MaterialClaim
from deeper_dive.retrieval import LexicalIndex
from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class ClaimEvidenceCandidate:
    chunk_id: str
    source_id: str
    text: str
    origin: str
    location: str | None
    score: float
    relation_hint: str


class ClaimEvidenceRetriever:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.index = LexicalIndex(database)

    def retrieve(self, claim: MaterialClaim, *, limit: int = 12) -> list[ClaimEvidenceCandidate]:
        terms = [word.lower() for word in re.findall(r"[A-Za-z0-9]+", claim.text) if len(word) > 2]
        query = " OR ".join(dict.fromkeys(terms))
        hits = self.index.search(claim.project_id, query, limit=limit)
        if not hits:
            return []
        source_ids = tuple(dict.fromkeys(hit.source_id for hit in hits))
        placeholders = ",".join("?" for _ in source_ids)
        with self.database.connection() as db:
            rows = db.execute(
                f"SELECT id,origin FROM sources WHERE id IN ({placeholders})", source_ids
            ).fetchall()
        origins = {str(row["id"]): str(row["origin"]) for row in rows}
        claim_negated = self._negated(claim.text)
        return [
            ClaimEvidenceCandidate(
                hit.chunk_id,
                hit.source_id,
                hit.text,
                origins[hit.source_id],
                hit.location,
                hit.score,
                "contradicts" if self._negated(hit.text) != claim_negated else "supports",
            )
            for hit in hits
        ]

    @staticmethod
    def _negated(text: str) -> bool:
        return bool(
            re.search(r"\b(?:not|no|never|cannot|isn't|aren't|wasn't|weren't)\b", text.lower())
        )
