from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController, EpisodeLibraryScreen
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import CompletedUnitRecord, GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


def test_library_preserves_independent_run_states_and_actions(tmp_path: Path) -> None:
    asyncio.run(_library_workflow(tmp_path))


async def _library_workflow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Library")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episodes = EpisodeConfigurationService(database, clock=service.clock)
    paused = episodes.create(project.id, EpisodeConfiguration(title="Paused episode"))
    failed = episodes.create(project.id, EpisodeConfiguration(title="Failed episode"))
    complete = episodes.create(project.id, EpisodeConfiguration(title="Complete episode"))
    timestamp = format_timestamp(service.clock.now())
    for episode, state in ((paused, "paused"), (failed, "failed"), (complete, "completed")):
        service.runs(project.id).create(
            GenerationRunRecord(
                id=str(new_run_id()),
                episode_id=episode.id,
                stage="conversation" if state != "completed" else "export",
                state=state,
                created_at=timestamp,
                modified_at=timestamp,
                pause_requested=state == "paused",
                failure_code="fake_failure" if state == "failed" else None,
            )
        )

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        screen = EpisodeLibraryScreen()
        app.push_screen(screen)
        await pilot.pause()
        listing = str(screen.query_one("#episode-library-list", Static).render())
        assert "Paused episode | paused" in listing
        assert "Failed episode | failed" in listing
        assert "Complete episode | completed" in listing

        screen.selected_episode_id = failed.id
        screen.action_resume_selected()
        assert "Run state failed is not resumable" in str(
            screen.query_one("#screen-status", Static).render()
        )

        screen.selected_episode_id = paused.id
        screen.action_duplicate_selected()
        await pilot.pause()
        listing = str(screen.query_one("#episode-library-list", Static).render())
        assert "Paused episode Copy | draft" in listing
        assert len(service.hosts(project.id).list_episodes(project.id)) == 4

        screen.action_export_selected()
        assert (
            "no generation run to export"
            in str(screen.query_one("#screen-status", Static).render()).lower()
        )

        screen.action_request_delete()
        screen.action_cancel_delete()
        assert len(service.hosts(project.id).list_episodes(project.id)) == 4
        screen.action_request_delete()
        screen.action_confirm_delete()
        await pilot.pause()
        assert len(service.hosts(project.id).list_episodes(project.id)) == 3

        screen.action_new_episode()
        await pilot.pause()
        assert app.screen.id == "screen-episode"
        assert app.current_episode_id is None
        assert app.current_run_id is None


def test_library_resume_invokes_orchestration_from_checkpoint(tmp_path: Path) -> None:
    asyncio.run(_library_resume_invokes_orchestration_from_checkpoint(tmp_path))


async def _library_resume_invokes_orchestration_from_checkpoint(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _paused_resume_fixture(tmp_path)
    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    items = EpisodeLibraryController.items(app)
    item = next(item for item in items if item.episode.id == episode_id)

    resumed = EpisodeLibraryController.resume(app, item)
    assert resumed.id == run_id
    assert resumed.state == "pending"
    assert resumed.pause_requested is False
    await asyncio.wait_for(app.generation_monitor_controller.run(run_id), timeout=5.0)

    runs = service.runs(project_id)
    completed = runs.get(run_id)
    assert completed is not None
    assert completed.state == "completed"
    completed_stages = runs.list_completed_stages(run_id)
    assert set(completed_stages) == set(DEFAULT_STAGES)
    assert len(completed_stages) == len(DEFAULT_STAGES)


def test_library_resume_rejects_stale_run_without_mutating_selection(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _paused_resume_fixture(tmp_path)
    app = DeeperDiveApp(service)
    app.current_project_id = project_id
    item = next(row for row in EpisodeLibraryController.items(app) if row.episode.id == episode_id)
    assert item.run is not None
    service.runs(project_id).update(replace(item.run, state="pending", pause_requested=False))
    with pytest.raises(ValueError, match="run state pending is not resumable"):
        EpisodeLibraryController.resume(app, item)
    assert app.current_episode_id is None
    assert app.current_run_id is None
    current = service.runs(project_id).get(run_id)
    assert current is not None and current.state == "pending"


def test_library_resume_navigates_to_monitor_with_selected_run(tmp_path: Path) -> None:
    asyncio.run(_library_resume_navigates_to_monitor_with_selected_run(tmp_path))


async def _library_resume_navigates_to_monitor_with_selected_run(tmp_path: Path) -> None:
    service, project_id, episode_id, run_id = _paused_resume_fixture(tmp_path)
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project_id
        app.current_project_name = "Library resume"
        screen = EpisodeLibraryScreen()
        app.push_screen(screen)
        await pilot.pause()
        screen.selected_episode_id = episode_id
        screen.action_resume_selected()
        await pilot.pause()
        assert isinstance(app.screen, GenerationMonitorScreen)
        assert app.current_episode_id == episode_id
        assert app.current_run_id == run_id
        run = service.runs(project_id).get(run_id)
        assert run is not None
        assert run.state == "pending"


def _paused_resume_fixture(tmp_path: Path) -> tuple[DeeperDiveService, str, str, str]:
    service = _service(tmp_path)
    project = service.create_project("Library resume")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database, clock=service.clock).create(
        project.id,
        EpisodeConfiguration(title="Paused episode"),
    )
    timestamp = format_timestamp(service.clock.now())
    run_id = str(new_run_id())
    runs = service.runs(project.id)
    runs.create(
        GenerationRunRecord(
            id=run_id,
            episode_id=episode.id,
            stage="research",
            state="paused",
            created_at=timestamp,
            modified_at=timestamp,
            pause_requested=True,
        )
    )
    runs.complete_unit(CompletedUnitRecord(run_id, "sources", "stage", timestamp))
    runs.complete_unit(CompletedUnitRecord(run_id, "planning", "stage", timestamp))
    return service, project.id, episode.id, run_id


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)),
    )


def test_library_delete_confirmation_bound_to_project_and_selection(tmp_path: Path) -> None:
    asyncio.run(_library_delete_confirmation_bound_to_project_and_selection(tmp_path))


async def _library_delete_confirmation_bound_to_project_and_selection(tmp_path: Path) -> None:
    """A changed selection/project cannot consume a stale destructive confirmation."""
    service = _service(tmp_path)
    first = service.create_project("First")
    second = service.create_project("Second")
    first_config = EpisodeConfigurationService(
        Database(service.workspaces.project_root(first.id) / "project.db"),
        clock=service.clock,
    )
    second_config = EpisodeConfigurationService(
        Database(service.workspaces.project_root(second.id) / "project.db"),
        clock=service.clock,
    )
    alpha = first_config.create(first.id, EpisodeConfiguration(title="Alpha"))
    beta = first_config.create(first.id, EpisodeConfiguration(title="Beta"))
    gamma = second_config.create(second.id, EpisodeConfiguration(title="Gamma"))

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = first.id
        app.current_project_name = first.name
        screen = EpisodeLibraryScreen()
        app.push_screen(screen)
        await pilot.pause()

        screen.selected_episode_id = alpha.id
        screen.action_request_delete()
        assert screen.pending_delete_episode_id == alpha.id
        screen.selected_episode_id = beta.id
        screen.action_confirm_delete()
        assert screen.pending_delete_episode_id is None
        assert screen.pending_delete_project_id is None
        assert {item.id for item in service.hosts(first.id).list_episodes(first.id)} == {
            alpha.id,
            beta.id,
        }
        assert "cancelled" in str(screen.query_one("#screen-status", Static).render()).lower()

        # A project change must invalidate a confirmation, even if the episode
        # from the previous project remains as the selected screen identity.
        screen.selected_episode_id = alpha.id
        screen.action_request_delete()
        app.current_project_id = second.id
        screen.action_confirm_delete()
        assert {item.id for item in service.hosts(first.id).list_episodes(first.id)} == {
            alpha.id,
            beta.id,
        }
        assert [item.id for item in service.hosts(second.id).list_episodes(second.id)] == [gamma.id]

        app.current_project_id = first.id
        screen.selected_episode_id = beta.id
        screen.action_request_delete()
        screen.action_confirm_delete()
        screen.action_confirm_delete()  # Already consumed: never deletes again.
        assert [item.id for item in service.hosts(first.id).list_episodes(first.id)] == [alpha.id]


def test_library_renders_redacted_status_and_titles_literally(tmp_path: Path) -> None:
    asyncio.run(_library_renders_redacted_status_and_titles_literally(tmp_path))


async def _library_renders_redacted_status_and_titles_literally(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Literal library")
    episodes = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project.id) / "project.db"),
        clock=service.clock,
    )
    episodes.create(project.id, EpisodeConfiguration(title="Literal [REDACTED] title"))
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        screen = EpisodeLibraryScreen()
        app.push_screen(screen)
        await pilot.pause()

        listing = str(screen.query_one("#episode-library-list", Static).render())
        assert "Literal [REDACTED] title" in listing

        screen._status("Provider failed api_key=library-tui-canary")
        await pilot.pause()
        status = str(screen.query_one("#screen-status", Static).render())
        assert "api_key=[REDACTED]" in status
        assert "library-tui-canary" not in status
