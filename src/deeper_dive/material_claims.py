"""Material factual claim extraction linked to generated turn spans."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.host_turn import HostTurn
from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class ExtractedClaim:
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class MaterialClaim:
    id: str
    project_id: str
    episode_id: str
    turn_id: str
    text: str
    span_start: int
    span_end: int
    created_at: str


class ClaimExtractor(Protocol):
    def extract(self, text: str) -> list[ExtractedClaim]: ...


class SentenceClaimExtractor:
    """Deterministic baseline that keeps factual-looking sentences and drops filler/opinion."""

    _filler = re.compile(
        r"^(?:hello|hi|thanks|thank you|welcome|okay|ok|right|sure|exactly|absolutely|"
        r"let(?:'s| us) (?:move|continue|turn)|in my opinion|i think|i feel|i believe)\b",
        re.IGNORECASE,
    )
    _fact_signal = re.compile(
        r"\b(?:is|are|was|were|has|have|had|can|cannot|does|do|did|will|"
        r"\d+(?:\.\d+)?%?|19\d{2}|20\d{2})\b",
        re.IGNORECASE,
    )

    def extract(self, text: str) -> list[ExtractedClaim]:
        claims: list[ExtractedClaim] = []
        for match in re.finditer(r"[^.!?]+[.!?]?", text):
            sentence = match.group().strip()
            if not sentence or self._filler.search(sentence) or not self._fact_signal.search(sentence):
                continue
            start = match.start() + len(match.group()) - len(match.group().lstrip())
            claims.append(ExtractedClaim(sentence, start, start + len(sentence)))
        return claims


class MaterialClaimService:
    """Extract, validate, and durably persist material claims for one generated turn."""

    def __init__(
        self, database: Database, extractor: ClaimExtractor | None = None, *, clock: Clock | None = None
    ) -> None:
        self.database = database
        self.database.initialize()
        self.extractor = extractor or SentenceClaimExtractor()
        self.clock = SystemClock() if clock is None else clock
        self._ensure_schema()

    def extract_turn(self, project_id: str, turn: HostTurn) -> list[MaterialClaim]:
        extracted = self.extractor.extract(turn.text)
        claims: list[MaterialClaim] = []
        for item in extracted:
            if item.start < 0 or item.end <= item.start or item.end > len(turn.text):
                raise ValueError("claim span is outside generated turn")
            if turn.text[item.start:item.end] != item.text:
                raise ValueError("claim text must exactly match its turn span")
            claims.append(
                MaterialClaim(
                    str(uuid4()), project_id, turn.episode_id, turn.id, item.text,
                    item.start, item.end, format_timestamp(self.clock.now()),
                )
            )
        with self.database.transaction() as db:
            for claim in claims:
                db.execute(
                    """INSERT INTO material_claims(
                        id,project_id,episode_id,turn_id,text,span_start,span_end,created_at
                    ) VALUES (?,?,?,?,?,?,?,?)""",
                    (claim.id, claim.project_id, claim.episode_id, claim.turn_id, claim.text,
                     claim.span_start, claim.span_end, claim.created_at),
                )
        return claims

    def list_turn_claims(self, turn_id: str) -> list[MaterialClaim]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM material_claims WHERE turn_id=? ORDER BY span_start,id", (turn_id,)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def _ensure_schema(self) -> None:
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS material_claims (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                    turn_id TEXT NOT NULL REFERENCES conversation_turns(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    span_start INTEGER NOT NULL CHECK(span_start >= 0),
                    span_end INTEGER NOT NULL CHECK(span_end > span_start),
                    created_at TEXT NOT NULL
                )"""
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MaterialClaim:
        return MaterialClaim(
            id=str(row["id"]), project_id=str(row["project_id"]),
            episode_id=str(row["episode_id"]), turn_id=str(row["turn_id"]),
            text=str(row["text"]), span_start=int(row["span_start"]),
            span_end=int(row["span_end"]), created_at=str(row["created_at"]),
        )
