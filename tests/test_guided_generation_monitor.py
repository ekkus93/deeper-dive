from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from textual.widgets import Button, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager


def test_guided_monitor_failed_sources_run_routes_to_sources(tmp_path) -> None:
    asyncio.run(_guided_monitor_failed_sources_run_routes_to_sources(tmp_path))


async def _guided_monitor_failed_sources_run_routes_to_sources(tmp_path) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 10, 8, 12, 0, tzinfo=UTC)),
    )
    project = service.create_project("Repair")
    now = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Broken episode",
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
            "sources",
            "failed",
            now,
            now,
            failure_code="sources_missing",
            failure_message="No included source is ready.",
        )
    )
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_episode_id = episode_id
        app.current_run_id = run_id
        app.action_navigate("monitor")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedGenerationMonitorScreen)
        diagnostics = str(screen.query_one("#diagnostics-summary", Static).render())
        assert "Generation failed at stage sources" in diagnostics
        assert "sources_missing" in diagnostics
        repair = screen.query_one("#guided-monitor-repair", Button)
        assert repair.disabled is False
        repair.press()
        await pilot.pause()
        assert app.screen.id == "screen-sources"
