"""Validated structured decisions emitted by the conversation director."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class SegmentSignal(StrEnum):
    """How the current turn affects segment/episode progression."""

    CONTINUE = "continue"
    COMPLETE_SEGMENT = "complete_segment"
    COMPLETE_EPISODE = "complete_episode"


@dataclass(frozen=True, slots=True)
class DirectorDecision:
    """One bounded next-turn instruction produced by the director."""

    speaker_id: str
    intent: str
    evidence_ids: tuple[str, ...] = ()
    target_duration_seconds: int = 45
    target_words: int = 110
    handoff_instruction: str = ""
    segment_signal: SegmentSignal = SegmentSignal.CONTINUE

    def __post_init__(self) -> None:
        if not self.speaker_id.strip():
            raise ValueError("director decision requires a speaker")
        if not self.intent.strip():
            raise ValueError("director decision requires an intent")
        if self.target_duration_seconds <= 0:
            raise ValueError("target duration must be positive")
        if self.target_words <= 0:
            raise ValueError("target word count must be positive")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("director decision cannot repeat evidence IDs")

    def validate_scope(
        self,
        participating_host_ids: tuple[str, ...] | set[str],
        available_evidence_ids: tuple[str, ...] | set[str],
    ) -> None:
        """Reject decisions that escape the episode host/evidence scope."""

        hosts = set(participating_host_ids)
        evidence = set(available_evidence_ids)
        if self.speaker_id not in hosts:
            raise ValueError(f"director named non-participating host {self.speaker_id!r}")
        missing = [evidence_id for evidence_id in self.evidence_ids if evidence_id not in evidence]
        if missing:
            raise ValueError(f"director named nonexistent evidence IDs: {', '.join(missing)}")

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        participating_host_ids: tuple[str, ...] | set[str],
        available_evidence_ids: tuple[str, ...] | set[str],
    ) -> DirectorDecision:
        """Normalize a structured provider payload and enforce episode scope."""

        raw_evidence = payload.get("evidence_ids", ())
        if not isinstance(raw_evidence, (list, tuple)):
            raise ValueError("evidence_ids must be a list")
        try:
            signal = SegmentSignal(str(payload.get("segment_signal", SegmentSignal.CONTINUE)))
        except ValueError as exc:
            raise ValueError("invalid segment transition/completion signal") from exc
        decision = cls(
            speaker_id=str(payload.get("speaker_id", "")),
            intent=str(payload.get("intent", "")),
            evidence_ids=tuple(str(value) for value in raw_evidence),
            target_duration_seconds=int(payload.get("target_duration_seconds", 45)),
            target_words=int(payload.get("target_words", 110)),
            handoff_instruction=str(payload.get("handoff_instruction", "")),
            segment_signal=signal,
        )
        decision.validate_scope(participating_host_ids, available_evidence_ids)
        return decision
