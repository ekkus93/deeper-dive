from __future__ import annotations

from pathlib import Path

from deeper_dive.claim_verification import VerificationState
from deeper_dive.host_turn import HostTurn
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository, HostProfileRecord
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord
from deeper_dive.targeted_repair import TargetedRepairService


class Provider:
    def repair_turn(self, turn: HostTurn, feedback: str, evidence_ids: tuple[str, ...]) -> str:
        return f"repaired {turn.id}"


class Rechecker:
    def recheck_turn(self, turn: HostTurn) -> None:
        pass


class Summaries:
    def update_after_repair(self, episode_id: str, turn_id: str) -> None:
        pass


def test_section_repair_changes_only_repair_worthy_turns_in_selected_section(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    CorpusRepository(database).create_project(ProjectRecord("p", "Repair", "t", "t"))
    episodes = HostEpisodeRepository(database)
    episodes.create_host(HostProfileRecord("h", "p", "Host"))
    episodes.create_episode(EpisodeRecord("e", "p", "Episode", "t", "t"), ["h"])
    with database.transaction() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS conversation_turns (
            id TEXT PRIMARY KEY, episode_id TEXT, segment_ordinal INTEGER, turn_ordinal INTEGER,
            speaker_id TEXT, text TEXT, evidence_ids_json TEXT)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS material_claims (
            id TEXT PRIMARY KEY, project_id TEXT, episode_id TEXT, turn_id TEXT, text TEXT,
            span_start INTEGER, span_end INTEGER, created_at TEXT)"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS claim_verifications (
            claim_id TEXT PRIMARY KEY, state TEXT, rationale TEXT, confidence REAL,
            supporting_evidence_ids_json TEXT, contradicting_evidence_ids_json TEXT)"""
        )
        db.executemany(
            "INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?)",
            [
                ("t0", "e", 0, 0, "h", "bad zero", "[]"),
                ("t1", "e", 1, 0, "h", "bad one", "[]"),
                ("t2", "e", 1, 1, "h", "good one", "[]"),
            ],
        )
        for claim_id, turn_id in (("c0", "t0"), ("c1", "t1")):
            db.execute(
                "INSERT INTO material_claims VALUES (?,?,?,?,?,?,?,?)",
                (claim_id, "p", "e", turn_id, "bad", 0, 3, "t"),
            )
            db.execute(
                "INSERT INTO claim_verifications VALUES (?,?,?,?,?,?)",
                (claim_id, VerificationState.CONTRADICTED.value, "wrong", 1.0, "[]", "[]"),
            )

    repaired = TargetedRepairService(database, Provider(), Rechecker(), Summaries()).repair_section(
        "e", 1
    )
    assert [turn.id for turn in repaired] == ["t1"]
    with database.connection() as db:
        rows = db.execute("SELECT id,text FROM conversation_turns ORDER BY id").fetchall()
    assert [(row["id"], row["text"]) for row in rows] == [
        ("t0", "bad zero"),
        ("t1", "repaired t1"),
        ("t2", "good one"),
    ]
