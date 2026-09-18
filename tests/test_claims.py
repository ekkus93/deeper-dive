from __future__ import annotations

from deeper_dive.claims import Claim, ClaimEvidenceRepository, Evidence, EvidenceRelation
from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord, SourceChunkRecord, SourceRecord


def test_claim_can_hold_supporting_and_contradicting_evidence_without_changing_provenance(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s", "p", "user", "text", "Source", "now", locator="paper.pdf"))
    corpus.create_chunk(SourceChunkRecord("c1", "s", 0, "supports it", "h1", "page 1"))
    corpus.create_chunk(SourceChunkRecord("c2", "s", 1, "contradicts it", "h2", "page 2"))

    repository = ClaimEvidenceRepository(database)
    repository.create_claim(Claim("claim", "p", "The proposition", "now"))
    repository.add_evidence(Evidence("e1", "claim", "c1", EvidenceRelation.SUPPORTS, {"rank": 1}, {"checked": True}))
    repository.add_evidence(Evidence("e2", "claim", "c2", EvidenceRelation.CONTRADICTS, {"rank": 2}, {"checked": False}))

    assert repository.get_claim("claim") == Claim("claim", "p", "The proposition", "now")
    evidence = repository.list_evidence("claim")
    assert {item.relation for item in evidence} == {EvidenceRelation.SUPPORTS, EvidenceRelation.CONTRADICTS}
    assert evidence[0].retrieval_metadata == {"rank": 1}
    assert corpus.get_source("s").locator == "paper.pdf"
    assert corpus.list_chunks("s")[0].location == "page 1"


def test_all_evidence_relations_round_trip(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    corpus = CorpusRepository(database)
    corpus.create_project(ProjectRecord("p", "Project", "now", "now"))
    corpus.create_source(SourceRecord("s", "p", "user", "text", "Source", "now"))
    corpus.create_chunk(SourceChunkRecord("c", "s", 0, "text", "h"))
    repository = ClaimEvidenceRepository(database)
    repository.create_claim(Claim("claim", "p", "Claim", "now"))
    for index, relation in enumerate(EvidenceRelation):
        repository.add_evidence(Evidence(f"e{index}", "claim", "c", relation, {}, {}))
    assert {item.relation for item in repository.list_evidence("claim")} == set(EvidenceRelation)
