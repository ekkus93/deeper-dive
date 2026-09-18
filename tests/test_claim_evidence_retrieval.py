from __future__ import annotations

from pathlib import Path

from deeper_dive.claim_evidence_retrieval import ClaimEvidenceRetriever
from deeper_dive.material_claims import MaterialClaim
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def test_supporting_and_counterevidence_coexist_with_origin_and_location(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    repo = CorpusRepository(database)
    repo.create_project(ProjectRecord("p", "P", "t", "t"))
    repo.create_source(SourceRecord("s1", "p", "user", "text", "Primary", "t", "a", status="parsed"))
    repo.create_source(
        SourceRecord("s2", "p", "supplemental", "text", "Web", "t", "b", status="parsed")
    )
    repo.create_chunk(
        SourceChunkRecord("c1", "s1", 0, "Mars has two moons Phobos and Deimos.", "h1", "page 2")
    )
    repo.create_chunk(
        SourceChunkRecord(
            "c2",
            "s2",
            0,
            "Mars does not have two moons according to this disputed source.",
            "h2",
            "section 4",
        )
    )
    claim = MaterialClaim("cl", "p", "e", "t", "Mars has two moons.", 0, 19, "now")
    results = ClaimEvidenceRetriever(database).retrieve(claim)
    by_id = {item.chunk_id: item for item in results}
    assert by_id["c1"].relation_hint == "supports"
    assert by_id["c2"].relation_hint == "contradicts"
    assert by_id["c1"].origin == "user"
    assert by_id["c2"].origin == "supplemental"
    assert by_id["c1"].location == "page 2"
    assert by_id["c2"].location == "section 4"
