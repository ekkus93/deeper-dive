from __future__ import annotations

from deeper_dive.conversation_quality import ConversationQualityHeuristics, QualityIssueKind
from deeper_dive.host_turn import HostTurn


def _turn(i: int, speaker: str, text: str, evidence: tuple[str, ...] = ()) -> HostTurn:
    return HostTurn(str(i), "episode", 0, i, speaker, text, evidence)


def test_bad_fake_conversation_is_detected_and_gets_corrective_guidance() -> None:
    turns = [
        _turn(0, "a", "The measured value is 42.", ("good",)),
        _turn(1, "a", "Exactly."),
        _turn(2, "a", "Exactly."),
        _turn(3, "a", "The measured value is 42.", ("missing",)),
        _turn(4, "b", "Right."),
    ]
    heuristics = ConversationQualityHeuristics()
    issues = heuristics.inspect(
        turns,
        participating_host_ids={"a", "b"},
        allowed_evidence_ids={"good"},
    )
    kinds = {issue.kind for issue in issues}
    assert kinds == {
        QualityIssueKind.REPETITION,
        QualityIssueKind.MONOPOLY,
        QualityIssueKind.SHALLOW_ACKNOWLEDGEMENT,
        QualityIssueKind.UNSUPPORTED_CITATION,
    }
    correction = heuristics.corrective_instruction(issues)
    assert correction is not None
    assert "underrepresented" in correction
    assert "Regenerate" in correction


def test_good_multi_host_conversation_has_no_quality_issue() -> None:
    turns = [
        _turn(0, "a", "The primary source reports the measured value.", ("e1",)),
        _turn(1, "b", "The methodology explains how that value was obtained.", ("e2",)),
        _turn(2, "a", "A limitation is the small sample described in the appendix.", ("e3",)),
        _turn(3, "b", "That limitation changes how broadly we should generalize.", ("e3",)),
    ]
    heuristics = ConversationQualityHeuristics()
    issues = heuristics.inspect(
        turns,
        participating_host_ids={"a", "b"},
        allowed_evidence_ids={"e1", "e2", "e3"},
    )
    assert issues == ()
    assert heuristics.corrective_instruction(issues) is None
