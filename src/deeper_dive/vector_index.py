"""Persistent dependency-free vector index built on the project SQLite database."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass

from deeper_dive.embeddings import EmbeddingProvider
from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class VectorHit:
    chunk_id: str
    source_id: str
    score: float
    model_identity: str


class VectorIndex:
    """Persist vectors and perform exact cosine search for desktop-sized corpora.

    V1 deliberately uses an exact SQLite-backed scan: it is portable, restart-safe,
    dependency-free, and preserves stable chunk/provider identity. An ANN backend can
    replace the search implementation later without changing the provider contract.
    """

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS vector_index (
                    chunk_id TEXT NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    model_identity TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, model_identity)
                )"""
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS idx_vector_index_model ON vector_index(model_identity)"
            )

    def sync_project(self, project_id: str, provider: EmbeddingProvider) -> int:
        """Incrementally add/change vectors and remove stale vectors for one model."""

        identity = provider.metadata.identity
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT c.id,c.source_id,c.text,c.content_hash
                   FROM source_chunks c JOIN sources s ON s.id=c.source_id
                   WHERE s.project_id=? ORDER BY c.id""",
                (project_id,),
            ).fetchall()
            stored = {
                str(row["chunk_id"]): str(row["content_hash"])
                for row in db.execute(
                    """SELECT v.chunk_id,v.content_hash FROM vector_index v
                       JOIN sources s ON s.id=v.source_id
                       WHERE s.project_id=? AND v.model_identity=?""",
                    (project_id, identity),
                ).fetchall()
            }
        current = {str(row["id"]): str(row["content_hash"]) for row in rows}
        changed = [row for row in rows if stored.get(str(row["id"])) != str(row["content_hash"])]
        stale = set(stored) - set(current)
        vectors = provider.embed([str(row["text"]) for row in changed]) if changed else []
        if len(vectors) != len(changed):
            raise ValueError("embedding provider returned the wrong number of vectors")
        with self.database.transaction() as db:
            for chunk_id in stale:
                db.execute(
                    "DELETE FROM vector_index WHERE chunk_id=? AND model_identity=?",
                    (chunk_id, identity),
                )
            for row, vector in zip(changed, vectors, strict=True):
                if len(vector) != provider.metadata.dimensions:
                    raise ValueError("embedding vector dimensions do not match model metadata")
                db.execute(
                    """INSERT OR REPLACE INTO vector_index(
                        chunk_id,source_id,model_identity,content_hash,vector_json
                    ) VALUES (?,?,?,?,?)""",
                    (
                        str(row["id"]),
                        str(row["source_id"]),
                        identity,
                        str(row["content_hash"]),
                        json.dumps(vector, separators=(",", ":")),
                    ),
                )
        return len(changed) + len(stale)

    def rebuild_project(self, project_id: str, provider: EmbeddingProvider) -> int:
        identity = provider.metadata.identity
        with self.database.transaction() as db:
            db.execute(
                """DELETE FROM vector_index WHERE model_identity=? AND source_id IN
                   (SELECT id FROM sources WHERE project_id=?)""",
                (identity, project_id),
            )
        return self.sync_project(project_id, provider)

    def search(
        self, project_id: str, query: str, provider: EmbeddingProvider, *, limit: int = 10
    ) -> list[VectorHit]:
        if not query.strip() or limit <= 0:
            return []
        self.sync_project(project_id, provider)
        query_vector = provider.embed([query])[0]
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT v.chunk_id,v.source_id,v.vector_json
                   FROM vector_index v JOIN sources s ON s.id=v.source_id
                   WHERE s.project_id=? AND s.included=1 AND v.model_identity=?""",
                (project_id, provider.metadata.identity),
            ).fetchall()
        hits = [
            VectorHit(
                str(row["chunk_id"]),
                str(row["source_id"]),
                self._cosine(query_vector, json.loads(str(row["vector_json"]))),
                provider.metadata.identity,
            )
            for row in rows
        ]
        return sorted(hits, key=lambda hit: (-hit.score, hit.chunk_id))[:limit]

    @staticmethod
    def _cosine(left: list[float], right: list[float]) -> float:
        if len(left) != len(right):
            raise ValueError("vector dimensions differ")
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
