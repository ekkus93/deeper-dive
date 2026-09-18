"""Targeted repair of verified conversation turns without regenerating an episode."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from deeper_dive.claim_verification import VerificationState
from deeper_dive.host_turn import HostTurn
from deeper_dive.storage.database import Database


class TurnRepairProvider(Protocol):
    def repair_turn(
        self, turn: HostTurn, feedback: str, evidence_ids: tuple[str, ...]
    ) -> str: ...


class RepairRechecker(Protocol):
    def recheck_turn(self, turn: HostTurn) -> None: ...


class SummaryUpdater(Protocol):
    def update_after_repair(self, episode_id: str, turn_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class RepairCandidate:
    turn_id: str
    states: tuple[VerificationState, ...]


class TargetedRepairService:
    """Repair only affected turns while preserving unaffected turn identity/content."""

    REPAIR_STATES = {
        VerificationState.CONTRADICTED,
        VerificationState.PARTIALLY_SUPPORTED,
        VerificationState.INSUFFICIENT_EVIDENCE,
    }

    def __init__(
        self,
        database: Database,
        provider: TurnRepairProvider,
        rechecker: RepairRechecker,
        summary_updater: SummaryUpdater,
    ) -> None:
        self.database = database
        self.provider = provider
        self.rechecker = rechecker
        self.summary_updater = summary_updater

    def candidates(self, episode_id: str) -> list[RepairCandidate]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT mc.turn_id, cv.state
                FROM material_claims mc JOIN claim_verifications cv ON cv.claim_id=mc.id
                WHERE mc.episode_id=? ORDER BY mc.turn_id, mc.span_start""",
                (episode_id,),
            ).fetchall()
        grouped: dict[str, list[VerificationState]] = {}
        for row in rows:
            state = VerificationState(str(row["state"]))
            if state in self.REPAIR_STATES:
                grouped.setdefault(str(row["turn_id"]), []).append(state)
        return [
            RepairCandidate(turn_id, tuple(states)) for turn_id, states in grouped.items()
        ]

    def repair(self, turn_id: str) -> HostTurn:
        turn = self._turn(turn_id)
        feedback, evidence_ids = self._feedback(turn_id)
        text = self.provider.repair_turn(turn, feedback, evidence_ids).strip()
        if not text:
            raise ValueError("repair provider returned empty turn")
        repaired = HostTurn(
            turn.id,
            turn.episode_id,
            turn.segment_ordinal,
            turn.turn_ordinal,
            turn.speaker_id,
            text,
            evidence_ids,
        )
        with self.database.transaction() as db:
            db.execute(
                "UPDATE conversation_turns SET text=?,evidence_ids_json=? WHERE id=?",
                (repaired.text, json.dumps(repaired.evidence_ids), repaired.id),
            )
            db.execute("DELETE FROM material_claims WHERE turn_id=?", (turn_id,))
        self.rechecker.recheck_turn(repaired)
        self.summary_updater.update_after_repair(repaired.episode_id, repaired.id)
        return repaired

    def _turn(self, turn_id: str) -> HostTurn:
        with self.database.connection() as db:
            row = db.execute(
                "SELECT * FROM conversation_turns WHERE id=?", (turn_id,)
            ).fetchone()
        if row is None:
            raise KeyError(turn_id)
        return HostTurn(
            str(row["id"]),
            str(row["episode_id"]),
            int(row["segment_ordinal"]),
            int(row["turn_ordinal"]),
            str(row["speaker_id"]),
            str(row["text"]),
            tuple(json.loads(str(row["evidence_ids_json"]))),
        )

    def _feedback(self, turn_id: str) -> tuple[str, tuple[str, ...]]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT cv.state,cv.rationale,cv.supporting_evidence_ids_json,
                cv.contradicting_evidence_ids_json FROM material_claims mc
                JOIN claim_verifications cv ON cv.claim_id=mc.id WHERE mc.turn_id=?""",
                (turn_id,),
            ).fetchall()
        bad = [
            row
            for row in rows
            if VerificationState(str(row["state"])) in self.REPAIR_STATES
        ]
        if not bad:
            raise ValueError("turn has no claims requiring repair")
        feedback = "\n".join(f"{row['state']}: {row['rationale']}" for row in bad)
        ids: list[str] = []
        for row in bad:
            ids.extend(json.loads(str(row["supporting_evidence_ids_json"])))
            ids.extend(json.loads(str(row["contradicting_evidence_ids_json"])))
        return feedback, tuple(dict.fromkeys(ids))
