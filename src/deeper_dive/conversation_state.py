"""Persistent resumable state for multi-host conversation generation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class ConversationState:
    episode_id: str
    segment_ordinal: int = 0
    segment_turn: int = 0
    running_summary: str = ""
    unresolved_topics: tuple[str, ...] = ()
    recent_context_refs: tuple[str, ...] = ()
    participation: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.segment_ordinal < 0 or self.segment_turn < 0:
            raise ValueError("conversation progress cannot be negative")
        if any(count < 0 for count in self.participation.values()):
            raise ValueError("participation counts cannot be negative")


class ConversationStateRepository:
    """Store compact resumability state instead of requiring the full transcript in memory."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def get(self, episode_id: str) -> ConversationState | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM conversation_states WHERE episode_id=?", (episode_id,)
            ).fetchone()
        if row is None:
            return None
        return ConversationState(
            episode_id=str(row["episode_id"]),
            segment_ordinal=int(row["segment_ordinal"]),
            segment_turn=int(row["segment_turn"]),
            running_summary=str(row["running_summary"]),
            unresolved_topics=tuple(self._list(row["unresolved_topics_json"])),
            recent_context_refs=tuple(self._list(row["recent_context_refs_json"])),
            participation={
                str(key): int(value)
                for key, value in self._dict(row["participation_json"]).items()
            },
        )

    def save(self, state: ConversationState) -> None:
        state.__post_init__()
        with self.database.transaction() as connection:
            connection.execute(
                """INSERT INTO conversation_states(
                    episode_id, segment_ordinal, segment_turn, running_summary,
                    unresolved_topics_json, recent_context_refs_json, participation_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(episode_id) DO UPDATE SET
                    segment_ordinal=excluded.segment_ordinal,
                    segment_turn=excluded.segment_turn,
                    running_summary=excluded.running_summary,
                    unresolved_topics_json=excluded.unresolved_topics_json,
                    recent_context_refs_json=excluded.recent_context_refs_json,
                    participation_json=excluded.participation_json""",
                (
                    state.episode_id,
                    state.segment_ordinal,
                    state.segment_turn,
                    state.running_summary,
                    json.dumps(state.unresolved_topics),
                    json.dumps(state.recent_context_refs),
                    json.dumps(state.participation, sort_keys=True),
                ),
            )

    def update(
        self,
        episode_id: str,
        *,
        segment_ordinal: int | None = None,
        segment_turn: int | None = None,
        running_summary: str | None = None,
        unresolved_topics: tuple[str, ...] | None = None,
        recent_context_refs: tuple[str, ...] | None = None,
        participation: dict[str, int] | None = None,
    ) -> ConversationState:
        current = self.get(episode_id) or ConversationState(episode_id)
        updated = ConversationState(
            episode_id=episode_id,
            segment_ordinal=current.segment_ordinal if segment_ordinal is None else segment_ordinal,
            segment_turn=current.segment_turn if segment_turn is None else segment_turn,
            running_summary=current.running_summary if running_summary is None else running_summary,
            unresolved_topics=(
                current.unresolved_topics if unresolved_topics is None else unresolved_topics
            ),
            recent_context_refs=(
                current.recent_context_refs if recent_context_refs is None else recent_context_refs
            ),
            participation=current.participation if participation is None else participation,
        )
        self.save(updated)
        return updated

    @staticmethod
    def _list(value: str) -> list[Any]:
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise ValueError("conversation state list payload is invalid")
        return parsed

    @staticmethod
    def _dict(value: str) -> dict[str, Any]:
        parsed = json.loads(value)
        if not isinstance(parsed, dict):
            raise ValueError("conversation participation payload is invalid")
        return parsed
