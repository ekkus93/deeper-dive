from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


def test_episode_setup_screen_validates_missing_hosts_before_planning(tmp_path: Path) -> None:
    asyncio.run(_exercise_missing_hosts(tmp_path))


async def _exercise_missing_hosts(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Empty panel")
    app = DeeperDiveApp(service, provider_controller=_provider_controller(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodeSetupScreen)
        screen.query_one("#episode-title", Input).value = "No hosts yet"
        screen.action_build_plan()
        assert "Add at least one host" in _status_text(screen)


def test_episode_setup_screen_validates_missing_provider_role(tmp_path: Path) -> None:
    asyncio.run(_exercise_missing_provider(tmp_path))


async def _exercise_missing_provider(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Missing role")
    _create_host(service, project.id, "h1", "Host One")
    app = DeeperDiveApp(
        service, provider_controller=_provider_controller(tmp_path, configure=False)
    )
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodeSetupScreen)
        screen.query_one("#episode-title", Input).value = "Needs provider"
        screen.action_build_plan()
        assert "episode_planning" in _status_text(screen)


def test_episode_setup_screen_builds_and_persists_plan_through_production_service(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_complete_setup(tmp_path))


async def _exercise_complete_setup(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Planning")
    _create_host(service, project.id, "h1", "Explainer")
    _create_host(service, project.id, "h2", "Skeptic")
    app = DeeperDiveApp(service, provider_controller=_provider_controller(tmp_path))
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodeSetupScreen)
        screen.query_one("#episode-title", Input).value = "Deep Dive"
        screen.query_one("#episode-focus", Input).value = "Explain the corpus"
        screen.query_one("#episode-audience", Input).value = "engineers"
        screen.query_one("#episode-depth", Input).value = "technical"
        screen.query_one("#episode-duration", Input).value = "1200"
        screen.query_one("#episode-style", Input).value = "roundtable"
        screen.query_one("#episode-hosts", Input).value = "h2, h1"
        screen.query_one("#episode-must-cover", Input).value = "risks, evidence"
        screen.query_one("#episode-avoid", Input).value = "fluff"
        screen.query_one("#episode-research-policy", Input).value = "useful"
        screen.query_one("#episode-citation-behavior", Input).value = "cite-every-claim"
        screen.action_build_plan()
        assert "Plan built: 1 segments" in _status_text(screen)
        assert app.current_episode_id is not None

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config_service = EpisodeConfigurationService(database)
    episode = service.hosts(project.id).list_episodes(project.id)[0]
    config = config_service.load_configuration(episode.id)
    assert config.title == "Deep Dive"
    assert config.focus == "Explain the corpus"
    assert config.audience == "engineers"
    assert config.technical_depth == "technical"
    assert config.target_duration_seconds == 1200
    assert config.style == "roundtable"
    assert config.host_ids == ("h2", "h1")
    assert config.must_cover == ("risks", "evidence")
    assert config.avoid_topics == ("fluff",)
    assert config.research_overrides["policy"] == "useful"
    assert config.research_overrides["citation_behavior"] == "cite-every-claim"
    planner = EpisodePlannerService(database, _unused_generator())
    plan = planner.load_plan(episode.id)
    assert len(plan.segments) == 1
    assert plan.segments[0].title == "Opening"
    assert plan.target_duration_seconds == 1200


def _provider_controller(tmp_path: Path, *, configure: bool = True) -> ProviderController:
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
    if configure:
        config = store.load()
        config.defaults["episode_planning"] = "fake:fake-v1"
        store.save(config)
    return ProviderController(store, registry, {})


def _unused_generator():
    class UnusedGenerator:
        def generate_plan(self, request):  # pragma: no cover
            raise AssertionError("persisted plan should be loaded without generation")

    return UnusedGenerator()


def _create_host(service: DeeperDiveService, project_id: str, host_id: str, name: str) -> None:
    service.hosts(project_id).create_host(HostProfile(host_id, project_id, name).to_record())


def _status_text(screen: EpisodeSetupScreen) -> str:
    return str(screen.query_one("#screen-status", Static).render())
