from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from deeper_dive.claim_evidence_retrieval import ClaimEvidenceCandidate
from deeper_dive.claim_verification import ClaimVerificationService, VerificationState
from deeper_dive.material_claims import MaterialClaim
from deeper_dive.storage.database import Database


class StubGenerator:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.request: dict[str, object] | None = None

    def classify(self, request: dict[str, object]) -> dict[str, object]:
        self.request = request
        return self.payload


def _claim() -> MaterialClaim:
    return MaterialClaim("cl", "p", "e", "t", "Mars has two moons.", 0, 19, "now")


def _evidence() -> list[ClaimEvidenceCandidate]:
    return [
        ClaimEvidenceCandidate(
            "c1", "s1", "Mars has two moons.", "user", "page 2", 1.0, "supports"
        ),
        ClaimEvidenceCandidate(
            "c2",
            "s2",
            "Mars does not have two moons.",
            "supplemental",
            "section 4",
            0.8,
            "contradicts",
        ),
    ]


@pytest.mark.parametrize(
    "state",
    [
        VerificationState.SUPPORTED,
        VerificationState.PARTIALLY_SUPPORTED,
        VerificationState.CONTRADICTED,
        VerificationState.INSUFFICIENT_EVIDENCE,
        VerificationState.NOT_APPLICABLE,
    ],
)
def test_all_verification_states_are_schema_validated_and_persisted(
    tmp_path: Path, state: VerificationState
) -> None:
    generator = StubGenerator(
        {
            "state": state.value,
            "rationale": f"classified as {state.value}",
            "confidence": 0.75,
            "supporting_evidence_ids": ["c1"],
            "contradicting_evidence_ids": ["c2"],
        }
    )
    service = ClaimVerificationService(Database(tmp_path / "project.db"), generator)
    result = service.verify(_claim(), _evidence())
    assert result.state == state
    assert result.confidence == 0.75
    assert service.get("cl") == result
    assert generator.request is not None
    evidence = generator.request["evidence"]
    assert isinstance(evidence, list)
    assert evidence[0]["origin"] == "user"
    assert evidence[1]["location"] == "section 4"


def test_invalid_structured_output_and_out_of_scope_evidence_are_rejected(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    invalid = ClaimVerificationService(
        database, StubGenerator({"state": "maybe", "rationale": "invalid"})
    )
    with pytest.raises(ValidationError):
        invalid.verify(_claim(), _evidence())
    assert invalid.get("cl") is None

    outside = ClaimVerificationService(
        database,
        StubGenerator(
            {
                "state": "supported",
                "rationale": "bad citation",
                "supporting_evidence_ids": ["not-retrieved"],
            }
        ),
    )
    with pytest.raises(ValueError, match="outside retrieved scope"):
        outside.verify(_claim(), _evidence())
    assert outside.get("cl") is None


def test_verification_does_not_mutate_evidence_or_source_content(tmp_path: Path) -> None:
    evidence = _evidence()
    before = tuple(evidence)
    service = ClaimVerificationService(
        Database(tmp_path / "project.db"),
        StubGenerator(
            {
                "state": "partially_supported",
                "rationale": "sources disagree",
                "confidence": 0.6,
                "supporting_evidence_ids": ["c1"],
                "contradicting_evidence_ids": ["c2"],
            }
        ),
    )
    service.verify(_claim(), evidence)
    assert tuple(evidence) == before
    assert evidence[0].text == "Mars has two moons."
    assert evidence[1].text == "Mars does not have two moons."
