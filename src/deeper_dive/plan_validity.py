"""Shared persisted episode-plan validity policy."""

from __future__ import annotations

import hashlib
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
        for field in ("evidence_ids", "lead_host_ids"):
            value = payload.get(field, [])
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                issues.append(f"segment {segment.ordinal} {field} must be a list of strings")
        if "title" in payload and payload["title"] != segment.title:
            issues.append(f"segment {segment.ordinal} title disagrees with stored row")
        if "target_duration_seconds" in payload:
            duration = payload["target_duration_seconds"]
            if type(duration) is not int or duration != segment.target_duration_seconds:
                issues.append(f"segment {segment.ordinal} duration disagrees with stored row")
        for host_id in _strings(payload.get("lead_host_ids", [])):
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
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _project_indexed_evidence_ids(database: Database, project_id: str) -> set[str]:
    return set(CorpusRepository(database).list_indexed_chunk_ids(project_id))


def bind_generation_plan_revision(database: Database, run_id: str, episode_id: str) -> None:
    """Bind a run to immutable plan content, rejecting drift on legacy/new resume.

    Existing databases use the durable unit table; no destructive migration is
    required. A legacy run acquires its binding the first time it is observed.
    """
    with database.transaction() as db:
        run = db.execute("SELECT episode_id FROM generation_runs WHERE id=?", (run_id,)).fetchone()
        if run is None or run["episode_id"] != episode_id:
            raise ValueError("generation run does not belong to the selected episode")
        plan = db.execute(
            "SELECT * FROM episode_plans WHERE episode_id=?", (episode_id,)
        ).fetchone()
        if plan is None:
            return  # Automatic planning binds after it persists the initial plan.
        segments = db.execute(
            "SELECT ordinal,title,purpose,target_duration_seconds,segment_json "
            "FROM segment_plans WHERE episode_plan_id=? ORDER BY ordinal",
            (plan["id"],),
        ).fetchall()
        payload = [plan["id"], plan["plan_json"], [tuple(row) for row in segments]]
        revision = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        bindings = db.execute(
            "SELECT unit_id FROM generation_run_units WHERE run_id=? AND stage='plan_revision'",
            (run_id,),
        ).fetchall()
        if bindings and any(row["unit_id"] != revision for row in bindings):
            raise ValueError("generation plan revision changed; cannot resume the old run")
        db.execute(
            "INSERT OR IGNORE INTO generation_run_units(run_id,stage,unit_id,completed_at) "
            "VALUES (?,'plan_revision',?,datetime('now'))",
            (run_id, revision),
        )
