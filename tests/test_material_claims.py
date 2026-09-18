from __future__ import annotations

from pathlib import Path

from deeper_dive.host_turn import HostTurn, HostTurnService
from deeper_dive.material_claims import MaterialClaimService, SentenceClaimExtractor
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


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
    database = Database(tmp_path / "project.db")
    database.initialize()
    CorpusRepository(database).create_project(ProjectRecord("p", "Claims", "t", "t"))
    episodes = HostEpisodeRepository(database)
    episodes.create_host(HostProfileRecord("h1", "p", "Host"))
    episodes.create_episode(EpisodeRecord("e1", "p", "Episode", "t", "t"), ["h1"])
    HostTurnService(database, _UnusedProvider())
    with database.transaction() as db:
        db.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("t1", "e1", 0, 0, "h1", "Hi. The study has 12 participants.", "[]"),
        )
    turn = HostTurn("t1", "e1", 0, 0, "h1", "Hi. The study has 12 participants.", ())
    service = MaterialClaimService(database)
    created = service.extract_turn("p", turn)
    persisted = service.list_turn_claims("t1")
    assert len(created) == 1
    assert persisted == created
    assert turn.text[created[0].span_start : created[0].span_end] == created[0].text
    assert created[0].text == "The study has 12 participants."


class _UnusedProvider:
    def generate_turn(self, decision: object) -> dict[str, object]:
        raise AssertionError("not used")
