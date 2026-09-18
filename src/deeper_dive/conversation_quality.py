"""Deterministic conversation-quality diagnostics and corrective guidance."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from deeper_dive.host_turn import HostTurn


class QualityIssueKind(StrEnum):
    REPETITION = "repetition"
    MONOPOLY = "monopoly"
    SHALLOW_ACKNOWLEDGEMENT = "shallow_acknowledgement"
    UNSUPPORTED_CITATION = "unsupported_citation"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    kind: QualityIssueKind
    turn_ids: tuple[str, ...]
    message: str
    corrective_instruction: str


class ConversationQualityHeuristics:
    """Flag deterministic quality failures and prescribe bounded correction."""

    ACKNOWLEDGEMENTS = {"yes", "yeah", "right", "exactly", "agreed", "absolutely", "sure"}

    def inspect(
        self,
        turns: list[HostTurn],
        *,
        participating_host_ids: set[str],
        allowed_evidence_ids: set[str],
    ) -> tuple[QualityIssue, ...]:
        issues: list[QualityIssue] = []
        issues.extend(self._unsupported(turns, allowed_evidence_ids))
        repetition = self._repetition(turns)
        if repetition is not None:
            issues.append(repetition)
        monopoly = self._monopoly(turns, participating_host_ids)
        if monopoly is not None:
            issues.append(monopoly)
        shallow = self._shallow(turns)
        if shallow is not None:
            issues.append(shallow)
        return tuple(issues)

    def corrective_instruction(self, issues: tuple[QualityIssue, ...]) -> str | None:
        if not issues:
            return None
        return " ".join(dict.fromkeys(issue.corrective_instruction for issue in issues))

    def _unsupported(self, turns: list[HostTurn], allowed: set[str]) -> list[QualityIssue]:
        result = []
        for turn in turns:
            invalid = tuple(eid for eid in turn.evidence_ids if eid not in allowed)
            if invalid:
                result.append(
                    QualityIssue(
                        QualityIssueKind.UNSUPPORTED_CITATION,
                        (turn.id,),
                        f"Unsupported evidence IDs: {', '.join(invalid)}",
                        "Regenerate the affected turn using only evidence IDs in director scope.",
                    )
                )
        return result

    def _repetition(self, turns: list[HostTurn]) -> QualityIssue | None:
        normalized = [" ".join(turn.text.lower().split()) for turn in turns]
        counts = Counter(normalized)
        repeated = {text for text, count in counts.items() if text and count >= 2}
        ids = tuple(
            turn.id for turn, text in zip(turns, normalized, strict=True) if text in repeated
        )
        if not ids:
            return None
        return QualityIssue(
            QualityIssueKind.REPETITION,
            ids,
            "Repeated turn text detected.",
            "Direct the next turn to add a distinct contribution; "
            "regenerate repeated turns if needed.",
        )

    def _monopoly(self, turns: list[HostTurn], hosts: set[str]) -> QualityIssue | None:
        if len(hosts) < 2 or len(turns) < 4:
            return None
        counts = Counter(turn.speaker_id for turn in turns)
        speaker, count = counts.most_common(1)[0]
        if count / len(turns) < 0.75:
            return None
        return QualityIssue(
            QualityIssueKind.MONOPOLY,
            tuple(turn.id for turn in turns if turn.speaker_id == speaker),
            f"Host {speaker} has {count}/{len(turns)} turns.",
            "Prefer an underrepresented participating host on the next director step.",
        )

    def _shallow(self, turns: list[HostTurn]) -> QualityIssue | None:
        ids = []
        for turn in turns:
            words = [word.strip(".,!?:;").lower() for word in turn.text.split()]
            if len(words) <= 4 and words and words[0] in self.ACKNOWLEDGEMENTS:
                ids.append(turn.id)
        if len(ids) < 2:
            return None
        return QualityIssue(
            QualityIssueKind.SHALLOW_ACKNOWLEDGEMENT,
            tuple(ids),
            "Excessive shallow acknowledgements detected.",
            "Require the next host contribution to add evidence, analysis, "
            "or a substantive question.",
        )
