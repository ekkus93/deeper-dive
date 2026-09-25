"""Bounded, durable and resumable host-turn generation."""

from __future__ import annotations

import json
import sqlite3
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


@dataclass(frozen=True, slots=True)
class HostTurnProviderIdentity:
    turn_id: str
    provider_id: str
    model: str


@dataclass(frozen=True, slots=True)
class HostTurnProvenance:
    """Durable provenance tying one generated turn to source passages."""

    turn_id: str
    episode_id: str
    segment_ordinal: int
    turn_ordinal: int
    host_id: str
    evidence_id: str
    source_id: str
    source_title: str
    source_locator: str | None
    chunk_id: str
    chunk_ordinal: int
    chunk_location: str | None
    source_passage: str
    claim_text: str


class HostTurnProvider(Protocol):
    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]: ...


class HostTurnService:
    """Generate one turn, then atomically persist turn, state, and run checkpoint."""

    STAGE = "conversation"

    def __init__(self, database: Database, provider: HostTurnProvider | None = None) -> None:
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
        if self.provider is None:
            raise RuntimeError("host-turn generation requires a configured provider")
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
        provider_identity = self._provider_identity(payload)
        turn = HostTurn(
            id=str(uuid4()),
            episode_id=episode_id,
            segment_ordinal=state.segment_ordinal,
            turn_ordinal=state.segment_turn,
            speaker_id=speaker_id,
            text=text,
            evidence_ids=evidence_ids,
        )
        self._commit(run_id, unit_id, turn, state, provider_identity)
        return turn

    def list_turns(self, episode_id: str) -> list[HostTurn]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM conversation_turns WHERE episode_id=? "
                "ORDER BY segment_ordinal,turn_ordinal",
                (episode_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def provider_identity(self, turn_id: str) -> HostTurnProviderIdentity | None:
        with self.database.connection() as db:
            row = db.execute(
                """SELECT turn_id,provider_id,model FROM conversation_turn_provider_identity
                WHERE turn_id=?""",
                (turn_id,),
            ).fetchone()
        if row is None:
            return None
        return HostTurnProviderIdentity(
            turn_id=str(row["turn_id"]),
            provider_id=str(row["provider_id"]),
            model=str(row["model"]),
        )

    def list_provenance(self, turn_id: str) -> tuple[HostTurnProvenance, ...]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT * FROM conversation_turn_provenance
                WHERE turn_id=? ORDER BY chunk_ordinal,chunk_id""",
                (turn_id,),
            ).fetchall()
        return tuple(HostTurnProvenance(**dict(row)) for row in rows)

    def _commit(
        self,
        run_id: str,
        unit_id: str,
        turn: HostTurn,
        previous: ConversationState,
        provider_identity: tuple[str, str] | None,
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
            self._insert_provenance(db, turn)
            if provider_identity is not None:
                db.execute(
                    """INSERT OR REPLACE INTO conversation_turn_provider_identity(
                        turn_id,provider_id,model
                    ) VALUES (?,?,?)""",
                    (turn.id, provider_identity[0], provider_identity[1]),
                )
            db.execute(
                """INSERT INTO conversation_states(
                    episode_id,segment_ordinal,segment_turn,running_summary,
                    unresolved_topics_json,recent_context_refs_json,participation_json
                ) VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    segment_ordinal=excluded.segment_ordinal, segment_turn=excluded.segment_turn,
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

    def _insert_provenance(self, db: sqlite3.Connection, turn: HostTurn) -> None:
        for evidence_id in turn.evidence_ids:
            row = db.execute(
                """SELECT c.id AS chunk_id,c.ordinal AS chunk_ordinal,c.text AS source_passage,
                c.location AS chunk_location,s.id AS source_id,s.title AS source_title,
                s.locator AS source_locator
                FROM source_chunks c JOIN sources s ON s.id=c.source_id
                WHERE c.id=?""",
                (evidence_id,),
            ).fetchone()
            if row is None:
                continue
            db.execute(
                """INSERT OR REPLACE INTO conversation_turn_provenance(
                    turn_id,episode_id,segment_ordinal,turn_ordinal,host_id,evidence_id,
                    source_id,source_title,source_locator,chunk_id,chunk_ordinal,
                    chunk_location,source_passage,claim_text
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    turn.id,
                    turn.episode_id,
                    turn.segment_ordinal,
                    turn.turn_ordinal,
                    turn.speaker_id,
                    evidence_id,
                    str(row["source_id"]),
                    str(row["source_title"]),
                    None if row["source_locator"] is None else str(row["source_locator"]),
                    str(row["chunk_id"]),
                    int(row["chunk_ordinal"]),
                    None if row["chunk_location"] is None else str(row["chunk_location"]),
                    str(row["source_passage"]),
                    turn.text,
                ),
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
                    text TEXT NOT NULL, evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                    UNIQUE(episode_id,segment_ordinal,turn_ordinal)
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS conversation_turn_provider_identity (
                    turn_id TEXT PRIMARY KEY REFERENCES conversation_turns(id) ON DELETE CASCADE,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS conversation_turn_provenance (
                    turn_id TEXT NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
                    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                    segment_ordinal INTEGER NOT NULL CHECK(segment_ordinal >= 0),
                    turn_ordinal INTEGER NOT NULL CHECK(turn_ordinal >= 0),
                    host_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE RESTRICT,
                    evidence_id TEXT NOT NULL,
                    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    source_title TEXT NOT NULL,
                    source_locator TEXT,
                    chunk_id TEXT NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
                    chunk_ordinal INTEGER NOT NULL CHECK(chunk_ordinal >= 0),
                    chunk_location TEXT,
                    source_passage TEXT NOT NULL,
                    claim_text TEXT NOT NULL,
                    PRIMARY KEY(turn_id,evidence_id)
                )"""
            )
            db.execute(
                """CREATE INDEX IF NOT EXISTS turn_provenance_episode_idx
                ON conversation_turn_provenance(episode_id,segment_ordinal,turn_ordinal)"""
            )

    @staticmethod
    def _unit_id(state: ConversationState) -> str:
        return f"{state.segment_ordinal}:{state.segment_turn}"

    @staticmethod
    def _provider_identity(payload: dict[str, object]) -> tuple[str, str] | None:
        provider_id = payload.get("provider_id")
        model = payload.get("model")
        if provider_id is None and model is None:
            return None
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("generated provider identity requires provider_id")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("generated provider identity requires model")
        return provider_id.strip(), model.strip()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> HostTurn:
        return HostTurn(
            id=str(row["id"]),
            episode_id=str(row["episode_id"]),
            segment_ordinal=int(row["segment_ordinal"]),
            turn_ordinal=int(row["turn_ordinal"]),
            speaker_id=str(row["speaker_id"]),
            text=str(row["text"]),
            evidence_ids=tuple(json.loads(str(row["evidence_ids_json"]))),
        )
