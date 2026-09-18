"""Bounded, durable and resumable host-turn generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from deeper_dive.conversation_state import ConversationState, ConversationStateRepository
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class HostTurn:
    id: str
    episode_id: str
    segment_ordinal: int
    turn_ordinal: int
    speaker_id: str
    text: str
    evidence_ids: tuple[str, ...]


class HostTurnProvider(Protocol):
    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]: ...


class HostTurnService:
    """Generate one turn, then atomically persist turn, state, and run checkpoint."""

    STAGE = "conversation"

    def __init__(self, database: Database, provider: HostTurnProvider) -> None:
        self.database = database
        self.database.initialize()
        self.provider = provider
        self.states = ConversationStateRepository(database)
        self._ensure_schema()

    def generate(self, run_id: str, episode_id: str, decision: DirectorDecision) -> HostTurn:
        state = self.states.get(episode_id) or ConversationState(episode_id)
        unit_id = self._unit_id(state)
        existing = self._checkpointed_turn(run_id, unit_id)
        if existing is not None:
            return existing

        payload = self.provider.generate_turn(decision)
        speaker_id = str(payload.get("speaker_id", ""))
        if speaker_id != decision.speaker_id:
            raise ValueError("generated turn speaker does not match director decision")
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ValueError("generated host turn must not be empty")
        words = text.split()
        hard_word_limit = max(decision.target_words * 2, decision.target_words + 50)
        if len(words) > hard_word_limit:
            text = " ".join(words[:hard_word_limit])
        raw_evidence = payload.get("evidence_ids", ())
        if not isinstance(raw_evidence, (list, tuple)):
            raise ValueError("generated evidence_ids must be a list")
        evidence_ids = tuple(str(value) for value in raw_evidence)
        if any(value not in decision.evidence_ids for value in evidence_ids):
            raise ValueError("generated turn cited evidence outside director scope")
        if len(set(evidence_ids)) != len(evidence_ids):
            raise ValueError("generated turn contains duplicate evidence IDs")

        turn = HostTurn(
            id=str(uuid4()),
            episode_id=episode_id,
            segment_ordinal=state.segment_ordinal,
            turn_ordinal=state.segment_turn,
            speaker_id=speaker_id,
            text=text,
            evidence_ids=evidence_ids,
        )
        self._commit(run_id, unit_id, turn, state)
        return turn

    def list_turns(self, episode_id: str) -> list[HostTurn]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM conversation_turns WHERE episode_id=? "
                "ORDER BY segment_ordinal,turn_ordinal",
                (episode_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def _commit(
        self, run_id: str, unit_id: str, turn: HostTurn, previous: ConversationState
    ) -> None:
        participation = dict(previous.participation)
        participation[turn.speaker_id] = participation.get(turn.speaker_id, 0) + 1
        refs = (*previous.recent_context_refs, turn.id)[-8:]
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO conversation_turns(
                    id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
                ) VALUES (?,?,?,?,?,?,?)""",
                (
                    turn.id,
                    turn.episode_id,
                    turn.segment_ordinal,
                    turn.turn_ordinal,
                    turn.speaker_id,
                    turn.text,
                    json.dumps(turn.evidence_ids),
                ),
            )
            db.execute(
                """INSERT INTO conversation_states(
                    episode_id,segment_ordinal,segment_turn,running_summary,
                    unresolved_topics_json,recent_context_refs_json,participation_json
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    segment_ordinal=excluded.segment_ordinal,
                    segment_turn=excluded.segment_turn,
                    running_summary=excluded.running_summary,
                    unresolved_topics_json=excluded.unresolved_topics_json,
                    recent_context_refs_json=excluded.recent_context_refs_json,
                    participation_json=excluded.participation_json""",
                (
                    turn.episode_id,
                    previous.segment_ordinal,
                    previous.segment_turn + 1,
                    previous.running_summary,
                    json.dumps(previous.unresolved_topics),
                    json.dumps(refs),
                    json.dumps(participation, sort_keys=True),
                ),
            )
            db.execute(
                """INSERT OR IGNORE INTO generation_run_units(run_id,stage,unit_id,completed_at)
                VALUES (?,?,?,CURRENT_TIMESTAMP)""",
                (run_id, self.STAGE, unit_id),
            )

    def _checkpointed_turn(self, run_id: str, unit_id: str) -> HostTurn | None:
        segment, ordinal = (int(value) for value in unit_id.split(":"))
        with self.database.connection() as db:
            checkpoint = db.execute(
                "SELECT 1 FROM generation_run_units WHERE run_id=? AND stage=? AND unit_id=?",
                (run_id, self.STAGE, unit_id),
            ).fetchone()
            if checkpoint is None:
                return None
            row = db.execute(
                "SELECT * FROM conversation_turns WHERE segment_ordinal=? AND turn_ordinal=? "
                "AND episode_id=(SELECT episode_id FROM generation_runs WHERE id=?)",
                (segment, ordinal, run_id),
            ).fetchone()
        return None if row is None else self._from_row(row)

    def _ensure_schema(self) -> None:
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS conversation_turns (
                    id TEXT PRIMARY KEY,
                    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                    segment_ordinal INTEGER NOT NULL CHECK(segment_ordinal >= 0),
                    turn_ordinal INTEGER NOT NULL CHECK(turn_ordinal >= 0),
                    speaker_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE RESTRICT,
                    text TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                    UNIQUE(episode_id,segment_ordinal,turn_ordinal)
                )"""
            )

    @staticmethod
    def _unit_id(state: ConversationState) -> str:
        return f"{state.segment_ordinal}:{state.segment_turn}"

    @staticmethod
    def _from_row(row: object) -> HostTurn:
        data = dict(row)  # type: ignore[arg-type]
        return HostTurn(
            id=str(data["id"]),
            episode_id=str(data["episode_id"]),
            segment_ordinal=int(data["segment_ordinal"]),
            turn_ordinal=int(data["turn_ordinal"]),
            speaker_id=str(data["speaker_id"]),
            text=str(data["text"]),
            evidence_ids=tuple(json.loads(str(data["evidence_ids_json"]))),
        )
