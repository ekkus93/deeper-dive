"""Structured claim verification classification and durable results."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from deeper_dive.claim_evidence_retrieval import ClaimEvidenceCandidate
from deeper_dive.material_claims import MaterialClaim
from deeper_dive.storage.database import Database


class VerificationState(StrEnum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


class VerificationOutput(BaseModel):
    """Strict structured output accepted from a verification model."""

    model_config = ConfigDict(extra="forbid")

    state: VerificationState
    rationale: str = Field(min_length=1, max_length=4000)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    supporting_evidence_ids: tuple[str, ...] = ()
    contradicting_evidence_ids: tuple[str, ...] = ()


class VerificationGenerator(Protocol):
    def classify(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class VerificationResult:
    claim_id: str
    state: VerificationState
    rationale: str
    confidence: float | None
    supporting_evidence_ids: tuple[str, ...]
    contradicting_evidence_ids: tuple[str, ...]


class ClaimVerificationService:
    """Validate model classifications, enforce evidence scope, and persist results."""

    def __init__(self, database: Database, generator: VerificationGenerator) -> None:
        self.database = database
        self.database.initialize()
        self.generator = generator
        self._ensure_schema()

    def verify(
        self, claim: MaterialClaim, evidence: list[ClaimEvidenceCandidate]
    ) -> VerificationResult:
        allowed = {item.chunk_id for item in evidence}
        request = {
            "claim": {"id": claim.id, "text": claim.text},
            "evidence": [
                {
                    "id": item.chunk_id,
                    "text": item.text,
                    "origin": item.origin,
                    "location": item.location,
                    "relation_hint": item.relation_hint,
                }
                for item in evidence
            ],
            "states": [state.value for state in VerificationState],
        }
        output = VerificationOutput.model_validate(self.generator.classify(request))
        cited = set(output.supporting_evidence_ids) | set(output.contradicting_evidence_ids)
        unknown = cited - allowed
        if unknown:
            raise ValueError(f"verification references evidence outside retrieved scope: {sorted(unknown)}")
        result = VerificationResult(
            claim.id,
            output.state,
            output.rationale,
            output.confidence,
            output.supporting_evidence_ids,
            output.contradicting_evidence_ids,
        )
        self._persist(result)
        return result

    def get(self, claim_id: str) -> VerificationResult | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM claim_verifications WHERE claim_id=?", (claim_id,)).fetchone()
        return None if row is None else self._from_row(row)

    def _persist(self, result: VerificationResult) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO claim_verifications(
                    claim_id,state,rationale,confidence,supporting_evidence_ids_json,
                    contradicting_evidence_ids_json
                ) VALUES (?,?,?,?,?,?)
                ON CONFLICT(claim_id) DO UPDATE SET
                    state=excluded.state,
                    rationale=excluded.rationale,
                    confidence=excluded.confidence,
                    supporting_evidence_ids_json=excluded.supporting_evidence_ids_json,
                    contradicting_evidence_ids_json=excluded.contradicting_evidence_ids_json""",
                (
                    result.claim_id,
                    result.state.value,
                    result.rationale,
                    result.confidence,
                    json.dumps(result.supporting_evidence_ids),
                    json.dumps(result.contradicting_evidence_ids),
                ),
            )

    def _ensure_schema(self) -> None:
        with self.database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS claim_verifications (
                    claim_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL CHECK(state IN (
                        'supported','partially_supported','contradicted',
                        'insufficient_evidence','not_applicable'
                    )),
                    rationale TEXT NOT NULL,
                    confidence REAL CHECK(confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
                    supporting_evidence_ids_json TEXT NOT NULL DEFAULT '[]',
                    contradicting_evidence_ids_json TEXT NOT NULL DEFAULT '[]'
                )"""
            )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> VerificationResult:
        return VerificationResult(
            claim_id=str(row["claim_id"]),
            state=VerificationState(str(row["state"])),
            rationale=str(row["rationale"]),
            confidence=None if row["confidence"] is None else float(row["confidence"]),
            supporting_evidence_ids=tuple(json.loads(str(row["supporting_evidence_ids_json"]))),
            contradicting_evidence_ids=tuple(json.loads(str(row["contradicting_evidence_ids_json"]))),
        )
