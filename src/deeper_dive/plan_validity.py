"""Shared persisted episode-plan validity policy."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from deeper_dive.conversation_state import ConversationStateRepository
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository

ALLOWED_GENERATION_PLAN_STATUSES = frozenset({"draft", "approved"})


@dataclass(frozen=True, slots=True)
class PlanValidity:
    """Usability result for a persisted episode plan."""

    usable: bool
    plan_id: str | None
    segment_count: int
    issues: tuple[str, ...] = ()


def evaluate_episode_plan(database: Database, episode_id: str) -> PlanValidity:
    """Return whether the selected episode has a usable persisted generation plan."""

    repository = HostEpisodeRepository(database)
    episode = repository.get_episode(episode_id)
    if episode is None:
        return PlanValidity(False, None, 0, (f"episode not found: {episode_id}",))
    plan = repository.get_plan(episode_id)
    if plan is None:
        return PlanValidity(False, None, 0, ("episode has no persisted plan",))

    issues: list[str] = []
    if plan.episode_id != episode_id:
        issues.append("plan belongs to a different episode")
    if plan.status not in ALLOWED_GENERATION_PLAN_STATUSES:
        issues.append(f"plan status {plan.status!r} is not usable for generation")
    try:
        plan_payload = json.loads(plan.plan_json)
    except json.JSONDecodeError:
        issues.append("plan JSON is invalid")
    else:
        if not isinstance(plan_payload, Mapping):
            issues.append("plan JSON payload must be an object")

    segments = tuple(repository.list_segments(plan.id))
    if not segments:
        issues.append("plan has no segments")
    _validate_segments(database, repository, episode.project_id, episode_id, segments, issues)
    return PlanValidity(not issues, plan.id, len(segments), tuple(issues))


def conversation_work_remains(database: Database, episode_id: str) -> bool:
    """Return whether host-generation work remains for the selected episode."""

    validity = evaluate_episode_plan(database, episode_id)
    if not validity.usable:
        return True
    state = ConversationStateRepository(database).get(episode_id)
    return state is None or state.segment_ordinal < validity.segment_count


def _validate_segments(
    database: Database,
    repository: HostEpisodeRepository,
    project_id: str,
    episode_id: str,
    segments: tuple[SegmentPlanRecord, ...],
    issues: list[str],
) -> None:
    host_ids = set(repository.list_episode_host_ids(episode_id))
    evidence_ids = _project_indexed_evidence_ids(database, project_id)
    for expected_ordinal, segment in enumerate(segments):
        if segment.ordinal != expected_ordinal:
            issues.append(
                f"segment ordinal {segment.ordinal} is not coherent at index {expected_ordinal}"
            )
        payload = _segment_payload(segment, issues)
        title = str(payload.get("title", segment.title)).strip() if payload else segment.title
        if not title.strip():
            issues.append(f"segment {segment.ordinal} requires a non-empty title")
        if segment.target_duration_seconds <= 0:
            issues.append(f"segment {segment.ordinal} duration must be positive")
        if payload is None:
            continue
        for host_id in _strings(payload.get("lead_host_ids", ())):
            if host_id not in host_ids:
                issues.append(
                    f"segment {segment.ordinal} names host {host_id!r} outside the episode"
                )
        for evidence_id in _strings(payload.get("evidence_ids", ())):
            if evidence_id not in evidence_ids:
                issues.append(
                    f"segment {segment.ordinal} references evidence {evidence_id!r} outside scope"
                )


def _segment_payload(
    segment: SegmentPlanRecord,
    issues: list[str],
) -> Mapping[str, object] | None:
    try:
        payload = json.loads(segment.segment_json)
    except json.JSONDecodeError:
        issues.append(f"segment {segment.ordinal} JSON is invalid")
        return None
    if not isinstance(payload, Mapping):
        issues.append(f"segment {segment.ordinal} JSON payload must be an object")
        return None
    return payload


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(item) for item in value)


def _project_indexed_evidence_ids(database: Database, project_id: str) -> set[str]:
    return set(CorpusRepository(database).list_indexed_chunk_ids(project_id))
