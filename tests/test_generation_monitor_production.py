from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_composed_monitor_runner_executes_durable_pipeline(tmp_path: Path) -> None:
    asyncio.run(_exercise_production_composed_monitor_runner(tmp_path))


async def _exercise_production_composed_monitor_runner(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"planner": ProviderConfig(provider_type="fake", default_model="fake-v1")},
            defaults={"episode_planning": "planner:fake-v1"},
        )
    )
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Production monitor")
    now = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=now,
            modified_at=now,
        ),
        [],
    )
    run_id = str(new_run_id())
    service.runs(project.id).create(
        GenerationRunRecord(
            run_id,
            episode_id,
            DEFAULT_STAGES[0],
            "pending",
            now,
            now,
        )
    )

    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    app.current_episode_id = episode_id
    app.current_run_id = run_id

    assert app.generation_monitor_controller.runner is not None
    await app.generation_monitor_controller.run(run_id)

    run = service.runs(project.id).get(run_id)
    assert run is not None
    assert run.state == "completed"
    assert set(service.runs(project.id).list_completed_stages(run_id)) == set(DEFAULT_STAGES)
