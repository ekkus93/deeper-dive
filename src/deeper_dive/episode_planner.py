"""Structured, evidence-aware episode planning service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.retrieval import LexicalIndex
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_plan_repository import EpisodePlanRepository
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)


class EpisodePlanGenerator(Protocol):
    """Normalized structured-output boundary used by the episode planner."""

    def generate_plan(self, request: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class PlannedSegment:
    title: str
    purpose: str
    target_duration_seconds: int
    questions: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    lead_host_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EpisodePlan:
    id: str
    episode_id: str
    segments: tuple[PlannedSegment, ...]

    @property
    def target_duration_seconds(self) -> int:
        return sum(segment.target_duration_seconds for segment in self.segments)


class EpisodePlannerService:
    """Build and persist bounded structured plans without starting dialogue or TTS."""

    def __init__(
        self,
        database: Database,
        generator: EpisodePlanGenerator,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.database = database
        self.generator = generator
        self.clock = SystemClock() if clock is None else clock
        self.configurations = EpisodeConfigurationService(database, clock=self.clock)
        self.repository = HostEpisodeRepository(database)
        self.plan_repository = EpisodePlanRepository(database)
        self.retrieval = LexicalIndex(database)

    def build_plan(self, episode_id: str) -> EpisodePlan:
        config = self.configurations.load_configuration(episode_id)
        episode = self.repository.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        evidence = self.retrieval.search(episode.project_id, config.focus, limit=12)
        request = {
            "episode": config.snapshot(),
            "evidence": [
                {
                    "chunk_id": hit.chunk_id,
                    "source_id": hit.source_id,
                    "text": hit.text,
                    "location": hit.location,
                }
                for hit in evidence
            ],
        }
        raw = self.generator.generate_plan(request)
        segments = self._validate_segments(raw, config.host_ids, {hit.chunk_id for hit in evidence})
        segments = self._bound_duration(segments, config.target_duration_seconds)
        plan = EpisodePlan(str(uuid4()), episode_id, tuple(segments))
        self._persist(plan)
        return plan

    def regenerate_plan(self, episode_id: str) -> EpisodePlan:
        return self.build_plan(episode_id)

    def regenerate_segment(self, episode_id: str, ordinal: int) -> EpisodePlan:
        current = self.load_plan(episode_id)
        if ordinal < 0 or ordinal >= len(current.segments):
            raise IndexError(ordinal)
        config = self.configurations.load_configuration(episode_id)
        request = {
            "episode": config.snapshot(),
            "segment": {"ordinal": ordinal, **self._segment_payload(current.segments[ordinal])},
            "mode": "regenerate_segment",
        }
        raw = self.generator.generate_plan(request)
        replacement = self._validate_segments(raw, config.host_ids, set())
        if len(replacement) != 1:
            raise ValueError("targeted regeneration must return exactly one segment")
        segments = list(current.segments)
        segments[ordinal] = replacement[0]
        segments = self._bound_duration(segments, config.target_duration_seconds)
        plan = EpisodePlan(current.id, episode_id, tuple(segments))
        self._persist(plan)
        return plan

    def edit_segment(self, episode_id: str, ordinal: int, segment: PlannedSegment) -> EpisodePlan:
        """Persist a user-edited segment while retaining plan identity and safety bounds."""

        current = self.load_plan(episode_id)
        if ordinal < 0 or ordinal >= len(current.segments):
            raise IndexError(ordinal)
        config = self.configurations.load_configuration(episode_id)
        validated = self._validate_segments(
            {"segments": [self._segment_payload(segment)]}, config.host_ids, set()
        )[0]
        segments = list(current.segments)
        segments[ordinal] = validated
        segments = self._bound_duration(segments, config.target_duration_seconds)
        plan = EpisodePlan(current.id, episode_id, tuple(segments))
        self._persist(plan)
        return plan

    def approve_plan(self, episode_id: str) -> EpisodePlan:
        """Mark the reviewed plan approved without starting dialogue or TTS."""

        plan = self.load_plan(episode_id)
        self._persist(plan, status="approved")
        return plan

    def load_plan(self, episode_id: str) -> EpisodePlan:
        record = self.repository.get_plan(episode_id)
        if record is None:
            raise KeyError(episode_id)
        segments = tuple(
            self._segment_from_payload(json.loads(item.segment_json))
            for item in self.repository.list_segments(record.id)
        )
        return EpisodePlan(record.id, episode_id, segments)

    def _persist(self, plan: EpisodePlan, *, status: str = "draft") -> None:
        timestamp = format_timestamp(self.clock.now())
        record = EpisodePlanRecord(
            id=plan.id,
            episode_id=plan.episode_id,
            status=status,
            plan_json=json.dumps({"target_duration_seconds": plan.target_duration_seconds}),
            created_at=timestamp,
            modified_at=timestamp,
        )
        segments = [
            SegmentPlanRecord(
                id=str(uuid4()),
                episode_plan_id=plan.id,
                ordinal=ordinal,
                title=segment.title,
                purpose=segment.purpose,
                target_duration_seconds=segment.target_duration_seconds,
                segment_json=json.dumps(self._segment_payload(segment), sort_keys=True),
            )
            for ordinal, segment in enumerate(plan.segments)
        ]
        self.plan_repository.replace(record, segments)

    @staticmethod
    def _validate_segments(
        raw: dict[str, Any], host_ids: tuple[str, ...], allowed_evidence: set[str]
    ) -> list[PlannedSegment]:
        items = raw.get("segments")
        if not isinstance(items, list) or not items:
            raise ValueError("episode plan must contain a non-empty segments list")
        segments: list[PlannedSegment] = []
        for item in items:
            if not isinstance(item, dict) or not str(item.get("title", "")).strip():
                raise ValueError("every segment requires a title")
            segment = EpisodePlannerService._segment_from_payload(item)
            if segment.target_duration_seconds <= 0:
                raise ValueError("segment duration must be positive")
            if any(host not in host_ids for host in segment.lead_host_ids):
                raise ValueError("segment names a host outside the episode")
            if allowed_evidence and any(
                eid not in allowed_evidence for eid in segment.evidence_ids
            ):
                raise ValueError("segment references evidence outside retrieved evidence")
            segments.append(segment)
        return segments

    @staticmethod
    def _bound_duration(segments: list[PlannedSegment], target: int) -> list[PlannedSegment]:
        total = sum(segment.target_duration_seconds for segment in segments)
        lower, upper = int(target * 0.9), int(target * 1.1)
        if lower <= total <= upper:
            return segments
        scale = target / total
        durations = [max(1, round(segment.target_duration_seconds * scale)) for segment in segments]
        durations[-1] += target - sum(durations)
        return [
            PlannedSegment(
                segment.title,
                segment.purpose,
                durations[index],
                segment.questions,
                segment.evidence_ids,
                segment.lead_host_ids,
            )
            for index, segment in enumerate(segments)
        ]

    @staticmethod
    def _segment_payload(segment: PlannedSegment) -> dict[str, Any]:
        return {
            "title": segment.title,
            "purpose": segment.purpose,
            "target_duration_seconds": segment.target_duration_seconds,
            "questions": list(segment.questions),
            "evidence_ids": list(segment.evidence_ids),
            "lead_host_ids": list(segment.lead_host_ids),
        }

    @staticmethod
    def _segment_from_payload(item: dict[str, Any]) -> PlannedSegment:
        return PlannedSegment(
            title=str(item.get("title", "")),
            purpose=str(item.get("purpose", "")),
            target_duration_seconds=int(item.get("target_duration_seconds", 0)),
            questions=tuple(str(value) for value in item.get("questions", ())),
            evidence_ids=tuple(str(value) for value in item.get("evidence_ids", ())),
            lead_host_ids=tuple(str(value) for value in item.get("lead_host_ids", ())),
        )
