"""Deterministic multi-host conversation directing policy."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.conversation_state import ConversationState
from deeper_dive.director_decision import DirectorDecision, SegmentSignal
from deeper_dive.episode_planner import PlannedSegment
from deeper_dive.hosts import HostProfile, HostRelationship


@dataclass(frozen=True, slots=True)
class DirectorPolicy:
    max_turns_per_segment: int = 12
    min_turns_per_segment: int = 1
    default_turn_seconds: int = 45

    def __post_init__(self) -> None:
        if self.max_turns_per_segment < 1 or self.min_turns_per_segment < 1:
            raise ValueError("director turn bounds must be positive")
        if self.min_turns_per_segment > self.max_turns_per_segment:
            raise ValueError("minimum turns cannot exceed maximum turns")


class DirectorEngine:
    """Select speakers and pace segments without any two-speaker alternation assumption."""

    def __init__(self, policy: DirectorPolicy | None = None) -> None:
        self.policy = policy or DirectorPolicy()

    def decide(
        self,
        segment: PlannedSegment,
        hosts: tuple[HostProfile, ...],
        state: ConversationState,
        *,
        relationships: tuple[HostRelationship, ...] = (),
        remaining_seconds: int | None = None,
    ) -> DirectorDecision:
        if not hosts:
            raise ValueError("director requires at least one participating host")
        host_ids = {host.id for host in hosts}
        if any(host.project_id != hosts[0].project_id for host in hosts):
            raise ValueError("participating hosts must belong to one project")
        lead_ids = set(segment.lead_host_ids) & host_ids
        counts = {host.id: state.participation.get(host.id, 0) for host in hosts}

        def score(host: HostProfile) -> tuple[int, int, int, str]:
            lead_penalty = 0 if host.id in lead_ids else 1
            role_text = f"{host.role} {host.expertise}".lower()
            purpose_words = {word for word in segment.purpose.lower().split() if len(word) > 3}
            role_penalty = -sum(1 for word in purpose_words if word in role_text)
            return (counts[host.id], lead_penalty, role_penalty, host.id)

        speaker = min(hosts, key=score)
        turn_number = state.segment_turn + 1
        remaining = (
            segment.target_duration_seconds if remaining_seconds is None else remaining_seconds
        )
        hard_stop = turn_number >= self.policy.max_turns_per_segment
        content_exhausted = remaining <= self.policy.default_turn_seconds // 2
        signal = (
            SegmentSignal.COMPLETE_SEGMENT
            if hard_stop or (turn_number >= self.policy.min_turns_per_segment and content_exhausted)
            else SegmentSignal.CONTINUE
        )
        duration = max(10, min(self.policy.default_turn_seconds, max(10, remaining)))
        evidence_ids = segment.evidence_ids
        intent = self._intent(segment, speaker, relationships, host_ids)
        handoff = self._handoff(hosts, speaker, counts, signal)
        decision = DirectorDecision(
            speaker_id=speaker.id,
            intent=intent,
            evidence_ids=evidence_ids,
            target_duration_seconds=duration,
            target_words=max(20, round(duration * 2.4)),
            handoff_instruction=handoff,
            segment_signal=signal,
        )
        decision.validate_scope(host_ids, set(segment.evidence_ids))
        return decision

    @staticmethod
    def _intent(
        segment: PlannedSegment,
        speaker: HostProfile,
        relationships: tuple[HostRelationship, ...],
        host_ids: set[str],
    ) -> str:
        base = f"Advance the segment purpose: {segment.purpose}"
        relevant = [
            relationship
            for relationship in relationships
            if relationship.from_host_id == speaker.id and relationship.to_host_id in host_ids
        ]
        if relevant:
            relation = relevant[0]
            return f"{base}. Engage {relation.to_host_id} as a {relation.stance}; stay evidence-grounded."
        return (
            f"{base}. Add a distinct evidence-grounded contribution rather than shallow agreement."
        )

    @staticmethod
    def _handoff(
        hosts: tuple[HostProfile, ...],
        speaker: HostProfile,
        counts: dict[str, int],
        signal: SegmentSignal,
    ) -> str:
        if signal is not SegmentSignal.CONTINUE:
            return "Conclude this segment concisely without opening a new topic."
        others = [host for host in hosts if host.id != speaker.id]
        if not others:
            return "Continue naturally; do not manufacture a second viewpoint."
        target = min(others, key=lambda host: (counts[host.id], host.id))
        return f"Leave a natural opening for {target.id}; do not manufacture disagreement."
