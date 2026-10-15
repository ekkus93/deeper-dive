"""Structured, evidence-aware episode planning service."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.plan_validity import PLAN_CONFIG_DIGEST_KEY, config_digest
from deeper_dive.retrieval import LexicalIndex
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_errors import (
    EpisodeConfigurationConflict,
    EpisodeConfigurationError,
)
from deeper_dive.storage.episode_plan_repository import EpisodePlanRepository
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    EpisodeRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository


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
        self.plan_repository.require_editable(episode_id)
        # One row read: the configuration and the revision it is persisted against
        # must come from the same snapshot, or a plan could be stored for an old
        # configuration under a newer revision.
        episode = self.repository.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        config, episode_revision = self._snapshot_of(episode)
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
        self._persist(plan, expected_episode_config_json=episode_revision)
        return plan

    def regenerate_plan(self, episode_id: str) -> EpisodePlan:
        return self.build_plan(episode_id)

    def regenerate_segment(self, episode_id: str, ordinal: int) -> EpisodePlan:
        self.plan_repository.require_editable(episode_id)
        # Snapshot first: any edit after this point either removes the plan (the
        # check below fails) or changes the revision (the persist CAS fails).
        config, episode_revision = self._snapshot(episode_id)
        try:
            current = self.load_plan(episode_id)
        except KeyError:
            raise EpisodeConfigurationConflict(
                "there is no plan to change (it was removed or never built); build the plan first"
            ) from None
        if ordinal < 0 or ordinal >= len(current.segments):
            raise IndexError(ordinal)
        self._require_plan_matches_revision(episode_id, episode_revision, current.id)
        request = {
            "episode": config.snapshot(),
            "segment": {"ordinal": ordinal, **self._segment_payload(current.segments[ordinal])},
            "mode": "regenerate_segment",
        }
        raw = self.generator.generate_plan(request)
        replacement = self._validate_segments(
            raw,
            config.host_ids,
            self._allowed_evidence_ids(episode_id),
        )
        if len(replacement) != 1:
            raise ValueError("targeted regeneration must return exactly one segment")
        segments = list(current.segments)
        segments[ordinal] = replacement[0]
        segments = self._bound_duration(segments, config.target_duration_seconds)
        plan = EpisodePlan(str(uuid4()), episode_id, tuple(segments))
        self._persist(plan, expected_episode_config_json=episode_revision)
        return plan

    def edit_segment(self, episode_id: str, ordinal: int, segment: PlannedSegment) -> EpisodePlan:
        """Replace one segment with a user edit within the safety bounds.

        The edited plan is persisted as a NEW plan (new id), so an approval of the
        plan a reviewer saw (``approve_plan(reviewed_plan_id=...)``) is rejected
        until they review the edited one.
        """

        self.plan_repository.require_editable(episode_id)
        # Snapshot first: any edit after this point either removes the plan (the
        # check below fails) or changes the revision (the persist CAS fails).
        config, episode_revision = self._snapshot(episode_id)
        try:
            current = self.load_plan(episode_id)
        except KeyError:
            raise EpisodeConfigurationConflict(
                "there is no plan to change (it was removed or never built); build the plan first"
            ) from None
        if ordinal < 0 or ordinal >= len(current.segments):
            raise IndexError(ordinal)
        self._require_plan_matches_revision(episode_id, episode_revision, current.id)
        validated = self._validate_segments(
            {"segments": [self._segment_payload(segment)]},
            config.host_ids,
            self._allowed_evidence_ids(episode_id),
        )[0]
        segments = list(current.segments)
        segments[ordinal] = validated
        segments = self._bound_duration(segments, config.target_duration_seconds)
        plan = EpisodePlan(str(uuid4()), episode_id, tuple(segments))
        self._persist(plan, expected_episode_config_json=episode_revision)
        return plan

    def approve_plan(self, episode_id: str, reviewed_plan_id: str | None = None) -> EpisodePlan:
        """Mark the reviewed plan approved without starting dialogue or TTS.

        ``reviewed_plan_id`` is the plan the caller showed the user. When another
        surface replaced it since (for example by regenerating), approval is
        refused instead of silently approving a plan nobody reviewed. Approving
        an already-approved plan again is an idempotent success.
        """

        # Capture the episode revision before reading the plan: approval is
        # compare-and-swapped against it so a concurrent edit cannot be followed
        # by re-publishing the plan that edit just invalidated.
        revision = self._episode_revision(episode_id)
        plan = self.load_plan(episode_id)
        if not plan.segments:
            raise EpisodeConfigurationError("The stored plan has no segments; regenerate the plan")
        if reviewed_plan_id is not None and plan.id != reviewed_plan_id:
            raise EpisodeConfigurationConflict(
                "the plan changed since you reviewed it; reload and review the current plan"
            )
        self.plan_repository.approve(
            plan.id,
            episode_id,
            format_timestamp(self.clock.now()),
            expected_episode_config_json=revision,
        )
        return plan

    def load_plan(self, episode_id: str) -> EpisodePlan:
        # One read: two reads could see a plan and the segments of its replacement.
        stored = self.repository.get_plan_with_segments(episode_id)
        if stored is None:
            raise KeyError(episode_id)
        record, items = stored
        segments = tuple(
            self._segment_from_payload(json.loads(item.segment_json)) for item in items
        )
        return EpisodePlan(record.id, episode_id, segments)

    def _persist(
        self,
        plan: EpisodePlan,
        *,
        status: str = "draft",
        expected_episode_config_json: str | None = None,
    ) -> None:
        timestamp = format_timestamp(self.clock.now())
        plan_payload: dict[str, object] = {"target_duration_seconds": plan.target_duration_seconds}
        if expected_episode_config_json is not None:
            # Fingerprint of the exact configuration this plan was built from, so
            # plan validity can reject a plan whose inputs have since changed.
            plan_payload[PLAN_CONFIG_DIGEST_KEY] = config_digest(expected_episode_config_json)
        record = EpisodePlanRecord(
            id=plan.id,
            episode_id=plan.episode_id,
            status=status,
            plan_json=json.dumps(plan_payload),
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
        self.plan_repository.replace(
            record,
            segments,
            expected_episode_config_json=expected_episode_config_json,
        )

    def _snapshot_of(self, episode: EpisodeRecord) -> tuple[EpisodeConfiguration, str]:
        return self.configurations.configuration_from_record(episode), episode.config_json

    def _snapshot(self, episode_id: str) -> tuple[EpisodeConfiguration, str]:
        """Configuration and revision from one episode row (never two separate reads)."""

        episode = self.repository.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        return self._snapshot_of(episode)

    def _require_plan_matches_revision(
        self, episode_id: str, revision: str, loaded_plan_id: str
    ) -> None:
        """Fail unless the stored plan is the one loaded and was built from ``revision``."""

        record = self.repository.get_plan(episode_id)
        if record is None or record.id != loaded_plan_id:
            raise EpisodeConfigurationConflict(
                "the plan was replaced or removed while it was being changed; "
                "reload the plan and retry"
            )
        try:
            built_from = json.loads(record.plan_json).get(PLAN_CONFIG_DIGEST_KEY)
        except (ValueError, AttributeError):
            return
        if built_from is not None and built_from != config_digest(revision):
            raise ValueError(
                "the plan was built from an older episode configuration; rebuild the plan"
            )

    def _episode_revision(self, episode_id: str) -> str:
        episode = self.repository.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        return episode.config_json

    def _allowed_evidence_ids(self, episode_id: str) -> set[str]:
        episode = self.repository.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        return set(CorpusRepository(self.database).list_indexed_chunk_ids(episode.project_id))

    @staticmethod
    def _validate_segments(
        raw: dict[str, Any],
        host_ids: tuple[str, ...],
        allowed_evidence: set[str] | None,
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
            if allowed_evidence is not None and any(
                eid not in allowed_evidence for eid in segment.evidence_ids
            ):
                raise ValueError("segment references evidence outside retrieved evidence")
            segments.append(segment)
        return segments

    @staticmethod
    def _bound_duration(segments: list[PlannedSegment], target: int) -> list[PlannedSegment]:
        if not segments or target < len(segments):
            raise ValueError("target duration cannot support one second per segment")
        total = sum(segment.target_duration_seconds for segment in segments)
        if any(segment.target_duration_seconds < 1 for segment in segments):
            raise ValueError("segment duration must be positive")
        lower, upper = int(target * 0.9), int(target * 1.1)
        if lower <= total <= upper:
            return segments
        # Reserve one second per segment, then apportion the remaining whole
        # seconds by largest remainder. Integer arithmetic avoids float drift.
        remaining = target - len(segments)
        weights = [segment.target_duration_seconds for segment in segments]
        durations = [1 + remaining * weight // total for weight in weights]
        order = sorted(
            range(len(segments)),
            key=lambda index: (-(remaining * weights[index] % total), index),
        )
        for index in order[: target - sum(durations)]:
            durations[index] += 1
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
        for field in ("evidence_ids", "lead_host_ids"):
            values = item.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError(f"{field} must be a list of strings")
        return PlannedSegment(
            title=str(item.get("title", "")),
            purpose=str(item.get("purpose", "")),
            target_duration_seconds=int(item.get("target_duration_seconds", 0)),
            questions=tuple(str(value) for value in item.get("questions", ())),
            evidence_ids=tuple(str(value) for value in item.get("evidence_ids", ())),
            lead_host_ids=tuple(str(value) for value in item.get("lead_host_ids", ())),
        )
