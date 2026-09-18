"""Durable claim/evidence domain persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from deeper_dive.storage.database import Database


class EvidenceRelation(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXTUALIZES = "contextualizes"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True, slots=True)
class Claim:
    id: str
    project_id: str
    text: str
    created_at: str


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    claim_id: str
    chunk_id: str
    relation: EvidenceRelation
    retrieval_metadata: dict[str, Any]
    verification_metadata: dict[str, Any]


class ClaimEvidenceRepository:
    """Persist assertions separately from immutable source/chunk provenance."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS claims (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )
            db.execute(
                """CREATE TABLE IF NOT EXISTS evidence_links (
                    id TEXT PRIMARY KEY,
                    claim_id TEXT NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                    chunk_id TEXT NOT NULL REFERENCES source_chunks(id) ON DELETE CASCADE,
                    relation TEXT NOT NULL CHECK(relation IN (
                        'supports','contradicts','contextualizes','uncertain'
                    )),
                    retrieval_metadata_json TEXT NOT NULL DEFAULT '{}',
                    verification_metadata_json TEXT NOT NULL DEFAULT '{}'
                )"""
            )

    def create_claim(self, claim: Claim) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO claims(id,project_id,text,created_at) VALUES (?,?,?,?)",
                (claim.id, claim.project_id, claim.text, claim.created_at),
            )

    def get_claim(self, claim_id: str) -> Claim | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        return None if row is None else Claim(**dict(row))

    def add_evidence(self, evidence: Evidence) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO evidence_links(
                    id,claim_id,chunk_id,relation,retrieval_metadata_json,verification_metadata_json
                ) VALUES (?,?,?,?,?,?)""",
                (
                    evidence.id,
                    evidence.claim_id,
                    evidence.chunk_id,
                    evidence.relation.value,
                    json.dumps(evidence.retrieval_metadata, sort_keys=True, separators=(",", ":")),
                    json.dumps(evidence.verification_metadata, sort_keys=True, separators=(",", ":")),
                ),
            )

    def list_evidence(self, claim_id: str) -> list[Evidence]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM evidence_links WHERE claim_id=? ORDER BY id", (claim_id,)
            ).fetchall()
        return [
            Evidence(
                id=str(row["id"]),
                claim_id=str(row["claim_id"]),
                chunk_id=str(row["chunk_id"]),
                relation=EvidenceRelation(str(row["relation"])),
                retrieval_metadata=json.loads(str(row["retrieval_metadata_json"])),
                verification_metadata=json.loads(str(row["verification_metadata_json"])),
            )
            for row in rows
        ]
