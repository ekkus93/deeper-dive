from __future__ import annotations

from deeper_dive.retrieval import LexicalIndex
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def test_lexical_index_is_persistent_incremental_and_filters_excluded(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s1", "p", "user", "text", "Alpha", "now"))
    corpus.create_source(
        SourceRecord("s2", "p", "user", "text", "Hidden", "now", included=False)
    )
    corpus.create_chunk(
        SourceChunkRecord(
            "c1", "s1", 0, "orchards grow apples and pears", "h1", "page 1"
        )
    )
    corpus.create_chunk(
        SourceChunkRecord("c2", "s1", 1, "quantum mechanics and photons", "h2")
    )
    corpus.create_chunk(
        SourceChunkRecord("c3", "s2", 0, "apples apples hidden orchard", "h3")
    )

    index = LexicalIndex(database)
    hits = index.search("p", "apples")
    assert [hit.chunk_id for hit in hits] == ["c1"]
    assert hits[0].source_id == "s1"
    assert hits[0].location == "page 1"
    assert hits[0].score > 0

    corpus.create_chunk(
        SourceChunkRecord("c4", "s1", 2, "apples are harvested in autumn", "h4")
    )
    assert {hit.chunk_id for hit in index.search("p", "apples")} == {"c1", "c4"}

    reopened = LexicalIndex(database)
    assert {hit.chunk_id for hit in reopened.search("p", "apples")} == {"c1", "c4"}

    corpus.delete_source("s1")
    assert reopened.search("p", "apples") == []


def test_lexical_index_returns_empty_for_empty_query_or_limit(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    CorpusRepository(database)
    index = LexicalIndex(database)
    assert index.search("missing", "") == []
    assert index.search("missing", "term", limit=0) == []
