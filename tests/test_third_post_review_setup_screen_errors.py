"""TPR-03: legacy Episode Setup reports frozen/conflicting edits instead of crashing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import (
    EpisodeConfigurationConflict,
    EpisodeConfigurationService,
    EpisodeFrozenError,
)
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


def _provider_controller(tmp_path: Path) -> ProviderController:
    registry = LLMProviderRegistry()
    registry.register(
        FakeLLMProvider(
            model="fake-v1",
            response=(
                '{"segments":[{"title":"Opening","purpose":"Explain evidence",'
                '"target_duration_seconds":1200,"lead_host_ids":["h2","h1"]}]}'
            ),
        )
    )
    store = UserConfigStore(tmp_path / "config.json")
    config = store.load()
    config.defaults["episode_planning"] = "fake:fake-v1"
    store.save(config)
    return ProviderController(store, registry, {})


def _status(screen: EpisodeSetupScreen) -> str:
    return str(screen.query_one("#screen-status", Static).render())


def test_frozen_episode_edit_is_reported_not_raised(tmp_path: Path) -> None:
    asyncio.run(_frozen(tmp_path))


def test_concurrent_episode_edit_is_reported_not_raised(tmp_path: Path) -> None:
    asyncio.run(_conflict(tmp_path))


async def _open_screen(
    tmp_path: Path,
) -> tuple[DeeperDiveService, DeeperDiveApp, str]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("P")
    for host_id, name in (("h1", "A"), ("h2", "B")):
        service.hosts(project.id).create_host(HostProfile(host_id, project.id, name).to_record())
    app = DeeperDiveApp(service, provider_controller=_provider_controller(tmp_path))
    return service, app, project.id


async def _frozen(tmp_path: Path) -> None:
    service, app, project_id = await _open_screen(tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project_id
        app.action_navigate("episode")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodeSetupScreen)
        # A successful Build Plan navigates to Generate; this test only needs the screen.
        app.action_navigate = lambda destination: None  # type: ignore[method-assign]
        screen.query_one("#episode-title", Input).value = "T"
        screen.query_one("#episode-hosts", Input).value = "h2, h1"
        screen.action_build_plan()
        episode_id = screen.current_episode_id
        assert episode_id is not None
        service.runs(project_id).create(
            GenerationRunRecord(
                "r1",
                episode_id,
                "sources",
                "completed",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            )
        )
        before = service.hosts(project_id).get_episode(episode_id)

        screen.query_one("#episode-title", Input).value = "Edited after generation"
        screen.action_build_plan()  # must not raise

        assert app.is_running
        assert "new episode" in _status(screen).lower()
        assert screen.query_one("#episode-title", Input).value == "Edited after generation"
        assert screen.current_episode_id == episode_id
        assert service.hosts(project_id).get_episode(episode_id) == before


async def _conflict(tmp_path: Path) -> None:
    service, app, project_id = await _open_screen(tmp_path)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project_id
        app.action_navigate("episode")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodeSetupScreen)
        # A successful Build Plan navigates to Generate; this test only needs the screen.
        app.action_navigate = lambda destination: None  # type: ignore[method-assign]
        screen.query_one("#episode-title", Input).value = "T"
        screen.query_one("#episode-hosts", Input).value = "h2, h1"
        screen.action_build_plan()
        episode_id = screen.current_episode_id
        assert episode_id is not None

        screen.query_one("#episode-title", Input).value = "Concurrent edit"

        # A REAL concurrent edit lands inside the race window: after the screen's
        # edit() has read the episode but before its compare-and-swap update runs.
        from dataclasses import replace

        from deeper_dive.storage.database import Database
        from deeper_dive.storage.episode_configuration import EpisodeConfigurationRepository

        other = EpisodeConfigurationService(
            Database(service.workspaces.project_root(project_id) / "project.db")
        )
        real_update = EpisodeConfigurationRepository.update

        def update_after_concurrent_edit(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            EpisodeConfigurationRepository.update = real_update  # type: ignore[method-assign]
            other.edit(
                episode_id,
                replace(other.load_configuration(episode_id), title="Edited elsewhere"),
            )
            return real_update(self, *args, **kwargs)

        with patch.object(EpisodeConfigurationRepository, "update", update_after_concurrent_edit):
            screen.action_build_plan()  # must not raise

        assert app.is_running
        assert "changed" in _status(screen).lower()
        stored = other.load_configuration(episode_id)
        assert stored.title == "Edited elsewhere"  # the other writer's edit survived
        assert screen.query_one("#episode-title", Input).value == "Concurrent edit"


def test_typed_errors_remain_value_errors() -> None:
    assert issubclass(EpisodeFrozenError, ValueError)
    assert issubclass(EpisodeConfigurationConflict, ValueError)
    with pytest.raises(ValueError):
        raise EpisodeFrozenError("frozen")
