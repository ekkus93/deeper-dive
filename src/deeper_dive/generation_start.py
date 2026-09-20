"""Durable, duplicate-safe generation run creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from deeper_dive.domain.clock import format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.storage.run_repositories import GenerationRunRecord

if TYPE_CHECKING:
    from deeper_dive.application.service import DeeperDiveService


_ACTIVE_STATES = frozenset({"pending", "running", "paused"})


@dataclass(frozen=True, slots=True)
class GenerationStartResult:
    """The durable run selected for a Generate action."""

    run: GenerationRunRecord
    created: bool


def select_or_create_generation_run(
    service: DeeperDiveService,
    project_id: str,
    episode_id: str,
) -> GenerationStartResult:
    """Return the active episode run or durably create one pending run.

    Repeated Generate actions are idempotent while a run remains active. Terminal
    runs do not block a later explicit generation attempt from creating a new run.
    """

    repository = service.runs(project_id)
    latest = repository.latest_for_episode(episode_id)
    if latest is not None and latest.state in _ACTIVE_STATES and not latest.cancel_requested:
        return GenerationStartResult(latest, False)

    now = format_timestamp(service.clock.now())
    run = GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode_id,
        stage="sources",
        state="pending",
        created_at=now,
        modified_at=now,
    )
    repository.create(run)
    return GenerationStartResult(run, True)
