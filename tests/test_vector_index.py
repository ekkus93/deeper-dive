from __future__ import annotations

from deeper_dive.embeddings import FakeEmbeddingProvider
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord, SourceChunkRecord, SourceRecord
from deeper_dive.vector_index import VectorIndex


def _corpus(database: Database) -> CorpusRepository:
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s", "p", "user", "text", "Source", "now"))
    corpus.create_chunk(SourceChunkRecord("c1", "s", 0, "alpha apples", "h1"))
    corpus.create_chunk(SourceChunkRecord("c2", "s", 1, "beta pears", "h2"))
    return corpus


def test_vector_index_persists_and_restart_reuses_unchanged_vectors(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    _corpus(database)
    provider = FakeEmbeddingProvider(dimensions=4)
    index = VectorIndex(database)
    assert index.sync_project("p", provider) == 2
    assert index.sync_project("p", provider) == 0
    reopened = VectorIndex(database)
    assert reopened.sync_project("p", provider) == 0
    hits = reopened.search("p", "apples", provider)
    assert {hit.chunk_id for hit in hits} == {"c1", "c2"}
    assert all(hit.model_identity == provider.metadata.identity for hit in hits)


def test_vector_index_incremental_remove_rebuild_and_exclusion(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = _corpus(database)
    provider = FakeEmbeddingProvider(dimensions=4)
    index = VectorIndex(database)
    assert index.sync_project("p", provider) == 2
    source = corpus.get_source("s")
    assert source is not None
    corpus.update_source(SourceRecord(**{**source.__dict__, "included": False}))
    assert index.search("p", "alpha", provider) == []
    corpus.delete_source("s")
    assert index.sync_project("p", provider) == 0
    assert index.rebuild_project("p", provider) == 0
