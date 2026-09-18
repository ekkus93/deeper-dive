"""Embedding provider contracts, deterministic test provider, and vector persistence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    """Identity and capabilities of one embedding model configuration."""

    provider: str
    model: str
    dimensions: int
    config_id: str = "default"

    @property
    def identity(self) -> str:
        return f"{self.provider}:{self.model}:{self.dimensions}:{self.config_id}"


class EmbeddingProvider(Protocol):
    """Normalized interface implemented by local and remote embedding backends."""

    @property
    def metadata(self) -> EmbeddingModel: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    """Deterministic, dependency-free embedding provider for tests and orchestration."""

    def __init__(self, *, dimensions: int = 4, model: str = "fake-v1") -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._metadata = EmbeddingModel("fake", model, dimensions)

    @property
    def metadata(self) -> EmbeddingModel:
        return self._metadata

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            vectors.append([digest[index] / 255.0 for index in range(self.metadata.dimensions)])
        return vectors


@dataclass(frozen=True, slots=True)
class StoredEmbedding:
    chunk_id: str
    model_identity: str
    vector: tuple[float, ...]


class EmbeddingStore:
    """Persist vectors keyed by chunk and exact provider/model/config identity."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS chunk_embeddings (
                    chunk_id TEXT NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
                    model_identity TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    PRIMARY KEY(chunk_id, model_identity)
                )"""
            )

    def put(self, chunk_id: str, metadata: EmbeddingModel, vector: list[float]) -> None:
        if len(vector) != metadata.dimensions:
            raise ValueError("vector dimensions do not match embedding model metadata")
        with self.database.transaction() as db:
            db.execute(
                """INSERT OR REPLACE INTO chunk_embeddings(chunk_id,model_identity,vector_json)
                   VALUES (?,?,?)""",
                (chunk_id, metadata.identity, json.dumps(vector, separators=(",", ":"))),
            )

    def get(self, chunk_id: str, metadata: EmbeddingModel) -> StoredEmbedding | None:
        with self.database.connection() as db:
            row = db.execute(
                """SELECT vector_json FROM chunk_embeddings
                   WHERE chunk_id=? AND model_identity=?""",
                (chunk_id, metadata.identity),
            ).fetchone()
        if row is None:
            return None
        vector = tuple(float(value) for value in json.loads(str(row["vector_json"])))
        return StoredEmbedding(chunk_id, metadata.identity, vector)
