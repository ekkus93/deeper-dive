# ruff: noqa: I001
"""Bounded, resumable production conversation generation across episode segments."""

from __future__ import annotations

# fmt: off

import json
from collections.abc import Callable
from dataclasses import dataclass, replace

from deeper_dive.conversation_state import ConversationState, ConversationStateRepository
from deeper_dive.director import DirectorEngine, DirectorPolicy
from deeper_dive.director_decision import DirectorDecision, SegmentSignal
from deeper_dive.episode_planner import PlannedSegment
from deeper_dive.host_turn import HostTurn, HostTurnProvider, HostTurnService
from deeper_dive.hosts import HostProfile, HostRelationship
from deeper_dive.pacing import DurationPacingController, PacingPolicy, PacingState
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository, SegmentPlanRecord

ConversationDecisionProvider = Callable[
    [PlannedSegment, tuple[HostProfile, ...], ConversationState, int],
    DirectorDecision,
]


@dataclass(frozen=True, slots=True)
class ConversationGenerationPolicy:
    """Hard safety bounds for one durable production conversation."""

    max_turns_per_segment: int = 12
    max_turns_per_episode: int = 128
    words_per_minute: float = 144.0
    default_turn_seconds: int = 45
    minimum_turn_words: int = 20

    def __post_init__(self) -> None:
        if self.max_turns_per_segment < 1:
            raise ValueError("max_turns_per_segment must be positive")
        if self.max_turns_per_episode < self.max_turns_per_segment:
            raise ValueError("max_turns_per_episode must cover at least one segment")
        if self.words_per_minute <= 0:
            raise ValueError("words_per_minute must be positive")
        if self.default_turn_seconds <= 0:
            raise ValueError("default_turn_seconds must be positive")
        if self.minimum_turn_words < 1:
            raise ValueError("minimum_turn_words must be positive")


class ConversationGenerationService:
    """Progress one episode through its durable plan without duplicating completed turns."""

    def __init__(
        self,
        database: Database,
        turn_provider: HostTurnProvider,
        *,
        decision_provider: ConversationDecisionProvider | None = None,
        available_evidence_ids: set[str] | frozenset[str] | None = None,
        policy: ConversationGenerationPolicy | None = None,
    ) -> None:
        self.database = database
        self.repository = HostEpisodeRepository(database)
        self.turns = HostTurnService(database, turn_provider)
        self.states = ConversationStateRepository(database)
        self.decision_provider = decision_provider
        self.available_evidence_ids = (
            None if available_evidence_ids is None else frozenset(available_evidence_ids)
        )
        self.policy = policy or ConversationGenerationPolicy()
        self.pacing = DurationPacingController(
            PacingPolicy(
                words_per_minute=self.policy.words_per_minute,
                max_turns_per_segment=self.policy.max_turns_per_segment,
                minimum_turn_words=self.policy.minimum_turn_words,
            )
        )
        self.fallback_director = DirectorEngine(
            DirectorPolicy(
                max_turns_per_segment=self.policy.max_turns_per_segment,
                min_turns_per_segment=1,
                default_turn_seconds=self.policy.default_turn_seconds,
            )
        )

    def run(self, run_id: str, episode_id: str) -> tuple[HostTurn, ...]:
        episode = self.repository.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        plan = self.repository.get_plan(episode_id)
        if plan is None:
            raise ValueError("conversation generation requires a persisted episode plan")
        segment_records = tuple(self.repository.list_segments(plan.id))
        if not segment_records:
            raise ValueError("conversation generation requires at least one planned segment")
        segments = tuple(self._segment(record) for record in segment_records)
        host_ids = tuple(self.repository.list_episode_host_ids(episode_id))
        hosts_by_id = {
            record.id: HostProfile.from_record(record)
            for record in self.repository.list_hosts(episode.project_id)
        }
        hosts = tuple(
            hosts_by_id[host_id] for host_id in host_ids if host_id in hosts_by_id
        )
        if len(hosts) != len(host_ids) or not hosts:
            raise ValueError("conversation generation requires all participating episode hosts")
        host_id_set = {host.id for host in hosts}
        relationships = tuple(
            HostRelationship.from_record(record)
            for record in self.repository.list_relationships(episode.project_id)
            if record.from_host_id in host_id_set and record.to_host_id in host_id_set
        )

        while True:
            state = self.states.get(episode_id) or ConversationState(episode_id)
            if state.segment_ordinal >= len(segments):
                return tuple(self.turns.list_turns(episode_id))

            existing_turns = self.turns.list_turns(episode_id)
            if len(existing_turns) >= self.policy.max_turns_per_episode:
                raise RuntimeError(
                    "conversation exceeded the maximum episode turn safety bound "
                    f"({self.policy.max_turns_per_episode})"
                )

            segment = segments[state.segment_ordinal]
            segment_turns = tuple(
                turn for turn in existing_turns if turn.segment_ordinal == state.segment_ordinal
            )
            pacing_state = PacingState(
                target_seconds=segment.target_duration_seconds,
                generated_words=sum(len(turn.text.split()) for turn in segment_turns),
                turn_count=len(segment_turns),
            )
            pacing = self.pacing.decide(
                pacing_state,
                desired_turn_seconds=self.policy.default_turn_seconds,
            )

            # Compatibility recovery for state written by the old one-turn stage or for
            # a process that stopped after a turn but before segment advancement existed.
            if segment_turns and pacing.should_complete:
                self.states.update(
                    episode_id,
                    segment_ordinal=state.segment_ordinal + 1,
                    segment_turn=0,
                )
                continue

            remaining_seconds = max(1, round(pacing.remaining_seconds))
            decision = self._decision(
                episode.title,
                segment,
                hosts,
                relationships,
                state,
                remaining_seconds,
            )
            decision.validate_scope(host_id_set, set(segment.evidence_ids))

            if (
                decision.segment_signal is SegmentSignal.CONTINUE
                and (
                    state.segment_turn + 1 >= self.policy.max_turns_per_segment
                    or pacing.remaining_words
                    <= max(decision.target_words, self.policy.minimum_turn_words)
                )
            ):
                decision = replace(decision, segment_signal=SegmentSignal.COMPLETE_SEGMENT)

            self.turns.generate(
                run_id,
                episode_id,
                decision,
                segment_count=len(segments),
            )

    def _decision(
        self,
        episode_title: str,
        segment: PlannedSegment,
        hosts: tuple[HostProfile, ...],
        relationships: tuple[HostRelationship, ...],
        state: ConversationState,
        remaining_seconds: int,
    ) -> DirectorDecision:
        if self.decision_provider is not None:
            return self.decision_provider(segment, hosts, state, remaining_seconds)
        return self.fallback_director.decide(
            segment,
            hosts,
            state,
            relationships=relationships,
            remaining_seconds=remaining_seconds,
        )

    def _segment(self, record: SegmentPlanRecord) -> PlannedSegment:
        try:
            payload = json.loads(record.segment_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"invalid persisted segment JSON at ordinal {record.ordinal}"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(
                f"invalid persisted segment payload at ordinal {record.ordinal}"
            )
        evidence_ids = tuple(str(value) for value in payload.get("evidence_ids", ()))
        if self.available_evidence_ids is not None:
            evidence_ids = tuple(
                evidence_id
                for evidence_id in evidence_ids
                if evidence_id in self.available_evidence_ids
            )
        return PlannedSegment(
            title=str(payload.get("title", record.title)).strip() or record.title,
            purpose=str(payload.get("purpose", record.purpose)),
            target_duration_seconds=record.target_duration_seconds,
            questions=tuple(str(value) for value in payload.get("questions", ())),
            evidence_ids=evidence_ids,
            lead_host_ids=tuple(str(value) for value in payload.get("lead_host_ids", ())),
        )

# fmt: on
