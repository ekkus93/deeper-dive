from __future__ import annotations

from pathlib import Path

from deeper_dive.claim_verification import ClaimVerificationService
from deeper_dive.host_turn import HostTurn, HostTurnService
from deeper_dive.material_claims import MaterialClaimService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.targeted_repair import TargetedRepairService


class RepairProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def repair_turn(self, turn: HostTurn, feedback: str, evidence_ids: tuple[str, ...]) -> str:
        self.calls.append(turn.id)
        assert "contradicted" in feedback
        assert evidence_ids == ("chunk-good", "chunk-bad")
        return "The corrected figure is 12 participants."


class Rechecker:
    def __init__(self) -> None:
        self.turns: list[HostTurn] = []

    def recheck_turn(self, turn: HostTurn) -> None:
        self.turns.append(turn)


class SummaryUpdater:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def update_after_repair(self, episode_id: str, turn_id: str) -> None:
        self.calls.append((episode_id, turn_id))


class UnusedTurnProvider:
    def generate_turn(self, decision: object) -> dict[str, object]:
        raise AssertionError("not used")


class UnusedVerifier:
    def classify(self, request: dict[str, object]) -> dict[str, object]:
        raise AssertionError("not used")


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "project.db")
    database.initialize()
    CorpusRepository(database).create_project(ProjectRecord("p", "Repair", "t", "t"))
    episodes = HostEpisodeRepository(database)
    episodes.create_host(HostProfileRecord("h1", "p", "Host"))
    episodes.create_episode(EpisodeRecord("e1", "p", "Episode", "t", "t"), ["h1"])
    HostTurnService(database, UnusedTurnProvider())
    MaterialClaimService(database)
    ClaimVerificationService(database, UnusedVerifier())
    with database.transaction() as db:
        db.executemany(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            [
                ("t1", "e1", 0, 0, "h1", "The figure is 10 participants.", "[]"),
                ("t2", "e1", 0, 1, "h1", "This unrelated turn stays unchanged.", "[]"),
            ],
        )
        db.execute(
            """INSERT INTO material_claims(
                id,project_id,episode_id,turn_id,text,span_start,span_end,created_at
            ) VALUES (?,?,?,?,?,?,?,?)""",
            ("c1", "p", "e1", "t1", "The figure is 10 participants.", 0, 30, "t"),
        )
        db.execute(
            """INSERT INTO claim_verifications(
                claim_id,state,rationale,confidence,supporting_evidence_ids_json,
                contradicting_evidence_ids_json
            ) VALUES (?,?,?,?,?,?)""",
            (
                "c1",
                "contradicted",
                "The primary source reports 12.",
                0.95,
                '["chunk-good"]',
                '["chunk-bad"]',
            ),
        )
    return database


def test_targeted_repair_changes_only_affected_turn_and_rechecks(tmp_path: Path) -> None:
    database = _database(tmp_path)
    provider = RepairProvider()
    rechecker = Rechecker()
    summaries = SummaryUpdater()
    service = TargetedRepairService(database, provider, rechecker, summaries)

    candidates = service.candidates("e1")
    assert [candidate.turn_id for candidate in candidates] == ["t1"]

    repaired = service.repair("t1")
    assert repaired.id == "t1"
    assert repaired.text == "The corrected figure is 12 participants."
    assert provider.calls == ["t1"]
    assert rechecker.turns == [repaired]
    assert summaries.calls == [("e1", "t1")]

    with database.connection() as db:
        rows = db.execute(
            "SELECT id,text FROM conversation_turns WHERE episode_id='e1' ORDER BY turn_ordinal"
        ).fetchall()
        old_claim = db.execute("SELECT 1 FROM material_claims WHERE id='c1'").fetchone()
    assert [(str(row["id"]), str(row["text"])) for row in rows] == [
        ("t1", "The corrected figure is 12 participants."),
        ("t2", "This unrelated turn stays unchanged."),
    ]
    assert old_claim is None


def test_repair_rejects_turn_without_repair_worthy_claim(tmp_path: Path) -> None:
    database = _database(tmp_path)
    service = TargetedRepairService(database, RepairProvider(), Rechecker(), SummaryUpdater())

    try:
        service.repair("t2")
    except ValueError as error:
        assert "no claims requiring repair" in str(error)
    else:
        raise AssertionError("expected repair to reject unaffected turn")
