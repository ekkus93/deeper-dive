from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.conversation_state import ConversationState, ConversationStateRepository
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.generation_start import (
    GenerationStartService,
    select_or_create_generation_run,
)
from deeper_dive.model_roles import ModelAssignment, ModelRole, ModelRoleAssignments
from deeper_dive.preflight import PreflightBlockedError
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    EpisodeRecord,
    SegmentPlanRecord,
)
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


@pytest.mark.parametrize("state", ["pending", "running", "paused"])
def test_generation_start_reuses_active_run(tmp_path: Path, state: str) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    active = _run(service, episode_id, state=state)
    service.runs(project_id).create(active)

    first = select_or_create_generation_run(service, project_id, episode_id)
    second = select_or_create_generation_run(service, project_id, episode_id)

    assert first.created is False
    assert first.run.id == active.id
    assert second.created is False
    assert second.run.id == active.id
    assert service.runs(project_id).latest_for_episode(episode_id) == active


@pytest.mark.parametrize("state", ["completed", "failed", "cancelled"])
def test_generation_start_creates_new_run_after_terminal_run(tmp_path: Path, state: str) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    terminal = _run(service, episode_id, state=state)
    service.runs(project_id).create(terminal)

    result = select_or_create_generation_run(service, project_id, episode_id)

    assert result.created is True
    assert result.run.id != terminal.id
    assert result.run.state == "pending"
    assert result.run.stage == "sources"


def test_generation_start_replaces_active_run_with_cancel_requested(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    cancelling = replace(_run(service, episode_id, state="running"), cancel_requested=True)
    service.runs(project_id).create(cancelling)

    result = select_or_create_generation_run(service, project_id, episode_id)

    assert result.created is True
    assert result.run.id != cancelling.id
    assert result.run.state == "pending"


def test_generation_start_rejects_unknown_persisted_state(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    service.runs(project_id).create(_run(service, episode_id, state="mystery"))

    with pytest.raises(ValueError, match="unsupported run state"):
        select_or_create_generation_run(service, project_id, episode_id)


def test_generation_start_requires_configured_execution_roles(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    assignments = ModelRoleAssignments(
        user={
            ModelRole.EPISODE_PLANNING: ModelAssignment("fake", "fake-v1"),
            ModelRole.HOST_GENERATION: ModelAssignment("fake", "fake-v1"),
            ModelRole.DIRECTING: ModelAssignment("fake", "fake-v1"),
            ModelRole.VERIFICATION: ModelAssignment("fake", "fake-v1"),
        },
    )

    roles = GenerationStartService(object())._required_model_roles(
        service.hosts(project_id),
        episode_id,
        assignments,
    )

    assert roles == (
        ModelRole.EPISODE_PLANNING,
        ModelRole.HOST_GENERATION,
        ModelRole.DIRECTING,
        ModelRole.VERIFICATION,
    )


def test_generation_start_treats_invalid_persisted_plan_as_missing(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    repository = service.hosts(project_id)
    timestamp = "2026-09-20T00:00:00.000000Z"
    repository.save_plan(
        EpisodePlanRecord("plan-1", episode_id, timestamp, timestamp, "approved", "{}"),
        [],
    )
    assignments = ModelRoleAssignments(
        user={
            ModelRole.EPISODE_PLANNING: ModelAssignment("fake", "fake-v1"),
            ModelRole.HOST_GENERATION: ModelAssignment("fake", "fake-v1"),
        },
    )

    roles = GenerationStartService(object())._required_model_roles(
        repository,
        episode_id,
        assignments,
    )

    assert roles[:2] == (ModelRole.EPISODE_PLANNING, ModelRole.HOST_GENERATION)


def test_generation_start_omits_host_generation_after_completed_conversation(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    repository = service.hosts(project_id)
    timestamp = "2026-09-20T00:00:00.000000Z"
    repository.save_plan(
        EpisodePlanRecord("plan-1", episode_id, timestamp, timestamp, "approved", "{}"),
        [
            SegmentPlanRecord(
                "segment-1",
                "plan-1",
                0,
                "Intro",
                target_duration_seconds=60,
                segment_json=json.dumps({"title": "Intro", "target_duration_seconds": 60}),
            ),
        ],
    )
    ConversationStateRepository(repository.database).save(
        ConversationState(episode_id, segment_ordinal=1)
    )

    roles = GenerationStartService(object())._required_model_roles(
        repository,
        episode_id,
        ModelRoleAssignments(),
    )

    assert roles == ()


def test_generation_start_preflight_blocks_before_run_creation(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"fake": ProviderConfig(provider_type="fake")},
            defaults={
                "episode_planning": "fake:fake-v1",
                "host_generation": "fake:fake-v1",
                "directing": "missing:fake-v1",
            },
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Preflight gate")
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(title="Episode", target_duration_seconds=1200),
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")

    starter = GenerationStartService(composition, ffmpeg_executable=ffmpeg)

    with pytest.raises(PreflightBlockedError, match="unknown provider"):
        starter.start(project.id, episode.id)
    assert composition.service.runs(project.id).latest_for_episode(episode.id) is None


def _run(
    service: DeeperDiveService,
    episode_id: str,
    *,
    state: str,
) -> GenerationRunRecord:
    timestamp = format_timestamp(service.clock.now())
    return GenerationRunRecord(
        id=str(new_run_id()),
        episode_id=episode_id,
        stage="export" if state == "completed" else "sources",
        state=state,
        created_at=timestamp,
        modified_at=timestamp,
    )


def _episode(tmp_path: Path) -> tuple[DeeperDiveService, str, str]:
    clock = FrozenClock(datetime(2026, 9, 20, 20, 0, tzinfo=UTC))
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"), clock=clock)
    project = service.create_project("Generation start")
    episode_id = str(new_episode_id())
    timestamp = format_timestamp(clock.now())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        [],
    )
    return service, project.id, episode_id
