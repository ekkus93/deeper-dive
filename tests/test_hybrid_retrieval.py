from __future__ import annotations

from deeper_dive.embeddings import FakeEmbeddingProvider
from deeper_dive.hybrid_retrieval import HybridRetriever
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def _database(tmp_path) -> Database:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s", "p", "user", "text", "Source", "now"))
    corpus.create_chunk(SourceChunkRecord("c1", "s", 0, "apples grow in orchards", "h1", "page 1"))
    corpus.create_chunk(SourceChunkRecord("c2", "s", 1, "pears grow on trees", "h2", "page 2"))
    return database


def test_lexical_only_mode_requires_no_embedding_provider(tmp_path) -> None:
    retriever = HybridRetriever(_database(tmp_path))
    hits = retriever.search("p", "apples")
    assert [hit.chunk_id for hit in hits] == ["c1"]
    assert hits[0].retrieval_mode == "lexical"
    assert hits[0].lexical_rank == 1
    assert hits[0].vector_rank is None
    assert hits[0].location == "page 1"


def test_hybrid_mode_fuses_candidates_and_preserves_provenance(tmp_path) -> None:
    retriever = HybridRetriever(
        _database(tmp_path), embedding_provider=FakeEmbeddingProvider(dimensions=4)
    )
    hits = retriever.search("p", "apples", limit=2)
    assert {hit.chunk_id for hit in hits} == {"c1", "c2"}
    apple = next(hit for hit in hits if hit.chunk_id == "c1")
    assert apple.lexical_rank == 1
    assert apple.vector_rank is not None
    assert apple.location == "page 1"
    assert apple.source_id == "s"
    assert all(hit.retrieval_mode == "hybrid" for hit in hits)
