"""FPR-02: the legacy Episode Plan screen reports service errors instead of crashing."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from guided_pilot import click
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_plan_screen import EpisodePlanScreen
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore

_PLAN = (
    '{"segments":[{"title":"Opening","purpose":"Explain evidence",'
    '"target_duration_seconds":1200,"lead_host_ids":["h2","h1"]}]}'
)


def _provider_controller(tmp_path: Path) -> ProviderController:
    registry = LLMProviderRegistry()
    registry.register(FakeLLMProvider(model="fake-v1", response=_PLAN))
    store = UserConfigStore(tmp_path / "config.json")
    config = store.load()
    config.defaults["episode_planning"] = "fake:fake-v1"
    store.save(config)
    return ProviderController(store, registry, {})


def _status(screen: EpisodePlanScreen) -> str:
    return str(screen.query_one("#screen-status", Static).render())


async def _open_plan(tmp_path: Path, *, with_run: bool):  # type: ignore[no-untyped-def]
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("P")
    for host_id, name in (("h1", "A"), ("h2", "B")):
        service.hosts(project.id).create_host(HostProfile(host_id, project.id, name).to_record())
    app = DeeperDiveApp(service, provider_controller=_provider_controller(tmp_path))
    return service, app, project.id


async def _reach_plan_screen(app, pilot, service, project_id, *, with_run):  # type: ignore[no-untyped-def]
    app.current_project_id = project_id
    app.action_navigate("episode")
    await pilot.pause()
    setup = app.screen
    assert isinstance(setup, EpisodeSetupScreen)
    setup.query_one("#episode-title", Input).value = "T"
    setup.query_one("#episode-hosts", Input).value = "h2, h1"
    await click(pilot, "#action-build-plan")
    app.action_navigate("plan")
    await pilot.pause()
    screen = app.screen
    assert isinstance(screen, EpisodePlanScreen)
    assert screen.plan is not None
    if with_run:
        service.runs(project_id).create(
            GenerationRunRecord(
                "r1",
                app.current_episode_id,
                "sources",
                "completed",
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
            )
        )
    return screen


@pytest.mark.parametrize("button", ["#action-regenerate-plan", "#action-regenerate-segment"])
def test_frozen_plan_regenerate_is_reported_not_raised(tmp_path: Path, button: str) -> None:
    async def run() -> None:
        service, app, project_id = await _open_plan(tmp_path, with_run=True)
        async with app.run_test(size=(120, 50)) as pilot:
            screen = await _reach_plan_screen(app, pilot, service, project_id, with_run=True)
            before = screen.plan
            await click(pilot, button)
            assert app.is_running
            assert app.return_code is None
            assert "frozen" in _status(screen).lower() or "new episode" in _status(screen).lower()
            assert screen.plan == before

    asyncio.run(run())


@pytest.mark.parametrize(
    "button,method",
    [
        ("#action-regenerate-plan", "regenerate_plan"),
        ("#action-regenerate-segment", "regenerate_segment"),
        ("#action-save-segment", "edit_segment"),
    ],
)
@pytest.mark.parametrize("error", [KeyError("gone"), OSError("disk"), RuntimeError("boom")])
def test_service_errors_are_reported_not_raised(
    tmp_path: Path, button: str, method: str, error: Exception
) -> None:
    async def run() -> None:
        service, app, project_id = await _open_plan(tmp_path, with_run=False)
        async with app.run_test(size=(120, 50)) as pilot:
            screen = await _reach_plan_screen(app, pilot, service, project_id, with_run=False)
            before = screen.plan
            controller = app.episode_plan_controller
            with patch.object(type(controller), method, side_effect=error):
                await click(pilot, button)
            assert app.is_running
            assert _status(screen) != "Status: Ready"
            assert screen.plan == before

    asyncio.run(run())
