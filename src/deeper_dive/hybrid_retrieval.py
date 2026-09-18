"""Hybrid lexical/vector retrieval with reciprocal-rank fusion and reranking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from deeper_dive.embeddings import EmbeddingProvider
from deeper_dive.retrieval import LexicalIndex
from deeper_dive.storage.database import Database
from deeper_dive.vector_index import VectorIndex


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk_id: str
    source_id: str
    text: str
    location: str | None
    score: float
    lexical_rank: int | None
    vector_rank: int | None
    retrieval_mode: str


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[RetrievalHit]) -> list[RetrievalHit]: ...


class ScoreReranker:
    """Deterministic baseline: fused score descending, then stable chunk ID."""

    def rerank(self, query: str, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        del query
        return sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))


class HybridRetriever:
    def __init__(
        self,
        database: Database,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        reranker: Reranker | None = None,
        rrf_k: int = 60,
    ) -> None:
        self.database = database
        self.lexical = LexicalIndex(database)
        self.provider = embedding_provider
        self.vector = None if embedding_provider is None else VectorIndex(database)
        self.reranker = ScoreReranker() if reranker is None else reranker
        self.rrf_k = rrf_k

    def search(self, project_id: str, query: str, *, limit: int = 10) -> list[RetrievalHit]:
        if limit <= 0 or not query.strip():
            return []
        candidate_limit = max(limit * 3, limit)
        lexical = self.lexical.search(project_id, query, limit=candidate_limit)
        vector = (
            []
            if self.provider is None or self.vector is None
            else self.vector.search(project_id, query, self.provider, limit=candidate_limit)
        )
        lexical_rank = {hit.chunk_id: rank for rank, hit in enumerate(lexical, 1)}
        vector_rank = {hit.chunk_id: rank for rank, hit in enumerate(vector, 1)}
        source_ids = {hit.chunk_id: hit.source_id for hit in lexical}
        source_ids.update({hit.chunk_id: hit.source_id for hit in vector})
        details = {hit.chunk_id: (hit.text, hit.location) for hit in lexical}
        missing = set(source_ids) - set(details)
        if missing:
            with self.database.connection() as db:
                placeholders = ",".join("?" for _ in missing)
                rows = db.execute(
                    f"SELECT id,text,location FROM source_chunks WHERE id IN ({placeholders})",  # noqa: S608
                    tuple(sorted(missing)),
                ).fetchall()
            details.update(
                {
                    str(row["id"]): (
                        str(row["text"]),
                        None if row["location"] is None else str(row["location"]),
                    )
                    for row in rows
                }
            )
        mode = "lexical" if self.provider is None else "hybrid"
        hits: list[RetrievalHit] = []
        for chunk_id, source_id in source_ids.items():
            lr = lexical_rank.get(chunk_id)
            vr = vector_rank.get(chunk_id)
            score = (0.0 if lr is None else 1.0 / (self.rrf_k + lr)) + (
                0.0 if vr is None else 1.0 / (self.rrf_k + vr)
            )
            text, location = details[chunk_id]
            hits.append(RetrievalHit(chunk_id, source_id, text, location, score, lr, vr, mode))
        return self.reranker.rerank(query, hits)[:limit]
