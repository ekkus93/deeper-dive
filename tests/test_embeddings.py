from __future__ import annotations

from deeper_dive.embeddings import EmbeddingModel, EmbeddingStore, FakeEmbeddingProvider
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def test_fake_embedding_provider_is_deterministic_and_reports_capabilities() -> None:
    provider = FakeEmbeddingProvider(dimensions=6)
    assert provider.metadata.provider == "fake"
    assert provider.metadata.dimensions == 6
    assert provider.embed(["same"])[0] == provider.embed(["same"])[0]
    assert provider.embed(["same"])[0] != provider.embed(["different"])[0]


def test_embedding_store_keys_vectors_by_exact_model_identity(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s", "p", "user", "text", "Source", "now"))
    corpus.create_chunk(SourceChunkRecord("c", "s", 0, "text", "hash"))
    store = EmbeddingStore(database)
    first = EmbeddingModel("fake", "one", 2)
    second = EmbeddingModel("fake", "two", 2)
    store.put("c", first, [0.1, 0.2])

    assert store.get("c", first) is not None
    assert store.get("c", second) is None

    store.put("c", second, [0.3, 0.4])
    assert store.get("c", first).vector == (0.1, 0.2)  # type: ignore[union-attr]
    assert store.get("c", second).vector == (0.3, 0.4)  # type: ignore[union-attr]
