from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


def test_episode_setup_planning_does_not_rebuild_production_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_exercise_no_rebuild(tmp_path, monkeypatch))


async def _exercise_no_rebuild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Planning")
    service.hosts(project.id).create_host(
        HostProfile("h1", project.id, "Explainer").to_record()
    )
    app = DeeperDiveApp(service, provider_controller=_provider_controller(tmp_path))

    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodeSetupScreen)
        screen.query_one("#episode-title", Input).value = "Deep Dive"
        screen.query_one("#episode-hosts", Input).value = "h1"
        monkeypatch.setattr(
            ProductionComposition,
            "build",
            classmethod(
                lambda cls, *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("planning must not rebuild production composition")
                )
            ),
        )

        screen.action_build_plan()

        assert "Plan built: 1 segments" in str(
            screen.query_one("#screen-status", Static).render()
        )


def _provider_controller(tmp_path: Path) -> ProviderController:
    registry = LLMProviderRegistry()
    registry.register(
        FakeLLMProvider(
            model="fake-v1",
            response=(
                '{"segments":[{"title":"Opening","purpose":"Explain evidence",'
                '"target_duration_seconds":1200,"lead_host_ids":["h1"]}]}'
            ),
        )
    )
    store = UserConfigStore(tmp_path / "config.json")
    config = store.load()
    config.defaults["episode_planning"] = "fake:fake-v1"
    store.save(config)
    return ProviderController(store, registry, {})
