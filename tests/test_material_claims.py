from __future__ import annotations

from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.host_turn import HostTurn
from deeper_dive.material_claims import MaterialClaimService, SentenceClaimExtractor
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def test_claim_extraction_fixture_separates_facts_from_conversational_filler() -> None:
    text = (
        "Welcome back! I think this is fascinating. "
        "The archive has 42 documents. Water freezes at 0 degrees Celsius. "
        "Thanks for listening."
    )
    claims = SentenceClaimExtractor().extract(text)
    assert [claim.text for claim in claims] == [
        "The archive has 42 documents.",
        "Water freezes at 0 degrees Celsius.",
    ]
    assert all(text[claim.start : claim.end] == claim.text for claim in claims)


def test_material_claims_persist_with_exact_turn_spans(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Claims")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    hosts = service.hosts(project.id)
    with database.transaction() as db:
        db.execute(
            "INSERT INTO hosts(id,project_id,name,created_at,modified_at) VALUES (?,?,?,?,?)",
            ("h1", project.id, "Host", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
        db.execute(
            "INSERT INTO episodes(id,project_id,title,state,config_json,created_at,modified_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                "e1",
                project.id,
                "Episode",
                "draft",
                "{}",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            ),
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS conversation_turns (
                id TEXT PRIMARY KEY, episode_id TEXT NOT NULL, segment_ordinal INTEGER NOT NULL,
                turn_ordinal INTEGER NOT NULL, speaker_id TEXT NOT NULL, text TEXT NOT NULL,
                evidence_ids_json TEXT NOT NULL DEFAULT '[]')"""
        )
        db.execute(
            "INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?)",
            ("t1", "e1", 0, 0, "h1", "Hi. The study has 12 participants.", "[]"),
        )
    turn = HostTurn("t1", "e1", 0, 0, "h1", "Hi. The study has 12 participants.", ())
    claim_service = MaterialClaimService(database)
    created = claim_service.extract_turn(project.id, turn)
    persisted = claim_service.list_turn_claims("t1")
    assert len(created) == 1
    assert persisted == created
    assert turn.text[created[0].span_start : created[0].span_end] == created[0].text
    assert created[0].text == "The study has 12 participants."
    assert hosts is not None
