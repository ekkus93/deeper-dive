from __future__ import annotations

import pytest

from deeper_dive.director_decision import DirectorDecision, SegmentSignal


def test_director_decision_normalizes_all_structured_fields() -> None:
    decision = DirectorDecision.from_payload(
        {
            "speaker_id": "host-2",
            "intent": "challenge the causal claim with the primary evidence",
            "evidence_ids": ["chunk-7", "chunk-9"],
            "target_duration_seconds": 38,
            "target_words": 92,
            "handoff_instruction": "End by asking host-1 to reconcile the disagreement.",
            "segment_signal": "continue",
        },
        participating_host_ids=("host-1", "host-2", "host-3"),
        available_evidence_ids={"chunk-7", "chunk-9", "chunk-10"},
    )

    assert decision.speaker_id == "host-2"
    assert decision.intent.startswith("challenge")
    assert decision.evidence_ids == ("chunk-7", "chunk-9")
    assert decision.target_duration_seconds == 38
    assert decision.target_words == 92
    assert "host-1" in decision.handoff_instruction
    assert decision.segment_signal is SegmentSignal.CONTINUE


def test_director_cannot_name_host_outside_episode() -> None:
    with pytest.raises(ValueError, match="non-participating host"):
        DirectorDecision.from_payload(
            {"speaker_id": "intruder", "intent": "speak"},
            participating_host_ids=("host-1", "host-2"),
            available_evidence_ids=set(),
        )


def test_director_cannot_name_nonexistent_evidence() -> None:
    with pytest.raises(ValueError, match="nonexistent evidence"):
        DirectorDecision.from_payload(
            {
                "speaker_id": "host-1",
                "intent": "ground the answer",
                "evidence_ids": ["missing-chunk"],
            },
            participating_host_ids=("host-1",),
            available_evidence_ids={"chunk-1"},
        )


def test_director_decision_rejects_invalid_bounds_and_signal() -> None:
    with pytest.raises(ValueError, match="target duration"):
        DirectorDecision("host-1", "speak", target_duration_seconds=0)
    with pytest.raises(ValueError, match="transition/completion"):
        DirectorDecision.from_payload(
            {"speaker_id": "host-1", "intent": "speak", "segment_signal": "wander"},
            participating_host_ids=("host-1",),
            available_evidence_ids=set(),
        )


def test_segment_completion_signals_are_explicit() -> None:
    assert {signal.value for signal in SegmentSignal} == {
        "continue",
        "complete_segment",
        "complete_episode",
    }
