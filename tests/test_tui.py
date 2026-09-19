from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id, new_run_id
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry, ProviderHealth
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import (
    GLOBAL_SCREENS,
    PROJECT_SCREENS,
    DeeperDiveApp,
    HomeProjectsScreen,
    SourcesScreen,
)
from deeper_dive.user_config import UserConfig, UserConfigStore


def test_shell_navigates_all_destinations(tmp_path: Path) -> None:
    asyncio.run(_navigate_all_destinations(tmp_path))


async def _navigate_all_destinations(tmp_path: Path) -> None:
    app = DeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        assert app.screen.id == "screen-home"
        for destination in (*GLOBAL_SCREENS[1:], *PROJECT_SCREENS):
            await pilot.press(*_shortcut(destination))
            await pilot.pause()
            assert app.screen.id == f"screen-{destination}"
            assert app.screen.query_one("#screen-status") is not None


def test_shell_runs_at_minimum_terminal_size(tmp_path: Path) -> None:
    asyncio.run(_run_at_minimum_terminal_size(tmp_path))


async def _run_at_minimum_terminal_size(tmp_path: Path) -> None:
    app = DeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("1")
        await pilot.pause()
        assert app.screen.id == "screen-sources"
        await pilot.press("h")
        await pilot.pause()
        assert app.screen.id == "screen-home"


def test_home_projects_workflow_create_open_rename_delete_cancel(tmp_path: Path) -> None:
    asyncio.run(_home_projects_workflow(tmp_path))


async def _home_projects_workflow(tmp_path: Path) -> None:
    app = DeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        home = _home(app)
        home.query_one("#new-project-name", Input).value = "Alpha"
        home.action_create_project()
        await pilot.pause()
        assert "Alpha" in _text(home, "#project-list")
        assert "sources 0" in _text(home, "#project-list")

        home.query_one("#rename-project-name", Input).value = "Beta"
        home.action_rename_selected()
        await pilot.pause()
        assert "Beta" in _text(home, "#project-list")

        home.action_open_selected()
        await pilot.pause()
        assert app.current_project_name == "Beta"
        assert app.screen.id == "screen-sources"

        app.action_navigate("home")
        await pilot.pause()
        home = _home(app)
        home.action_request_delete()
        home.action_cancel_delete()
        await pilot.pause()
        assert "Beta" in _text(home, "#project-list")
        assert "Delete cancelled" in _text(home, "#screen-status")

        home.action_request_delete()
        home.action_confirm_delete()
        await pilot.pause()
        assert "No projects yet" in _text(home, "#project-list")


def test_home_projects_surface_interrupted_run_state(tmp_path: Path) -> None:
    asyncio.run(_home_projects_interrupted_run_state(tmp_path))


async def _home_projects_interrupted_run_state(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Interrupted")
    timestamp = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
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
    service.runs(project.id).create(
        GenerationRunRecord(
            id=str(new_run_id()),
            episode_id=episode_id,
            stage="conversation",
            state="paused",
            created_at=timestamp,
            modified_at=timestamp,
            pause_requested=True,
        )
    )

    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)):
        assert "pause requested" in _text(_home(app), "#project-list")


def test_sources_tui_add_inspect_toggle_and_delete(tmp_path: Path) -> None:
    asyncio.run(_sources_tui_workflow(tmp_path))


async def _sources_tui_workflow(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Sources")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("sources")
        await pilot.pause()
        sources = _sources(app)
        sources.query_one("#source-title", Input).value = "Notes"
        sources.query_one("#source-text", Input).value = "First line about evidence."
        sources.action_add_paste()
        await pilot.pause()

        assert "Primary sources:" in _text(sources, "#source-list")
        assert "Notes | included | parsed | pasted-text" in _text(sources, "#source-list")
        assert "Origin: user" in _text(sources, "#source-details")
        assert "Locator: paste://text" in _text(sources, "#source-details")
        assert "Parsed text" in _text(sources, "#source-text-preview")
        assert "First line about evidence." in _text(sources, "#source-text-preview")

        sources.action_toggle_included()
        await pilot.pause()
        assert "Notes | excluded | parsed | pasted-text" in _text(sources, "#source-list")

        sources.action_delete_selected()
        await pilot.pause()
        assert "No sources yet" in _text(sources, "#source-list")


def test_preflight_tui_surfaces_unhealthy_provider_blocker(tmp_path: Path) -> None:
    asyncio.run(_preflight_tui_unhealthy_provider(tmp_path))


async def _preflight_tui_unhealthy_provider(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("Preflight")
    service.add_pasted_source(project.id, "Notes", "Grounded evidence for generation.")
    service.hosts(project.id).create_host(
        HostProfile(
            id="host-1",
            project_id=project.id,
            display_name="Host One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(
        UserConfig(defaults={role.value: "fake:fake-v1" for role in ModelRole})
    )
    llm_registry = LLMProviderRegistry()
    llm_registry.register(UnhealthyLLM())
    app = DeeperDiveApp(
        service,
        provider_controller=ProviderController(
            config_store,
            llm_registry,
            {"fake-tts": FakeTTSProvider()},
        ),
        preflight_controller=PreflightController(ffmpeg_executable=ffmpeg),
    )
    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("generate")
        await pilot.pause()
        screen = _preflight(app)
        assert "Sources: 1 included / 1 indexed" in _text(screen, "#preflight-summary")
        assert "Hosts: 1" in _text(screen, "#preflight-summary")
        assert "Expected duration: 20.0 minutes" in _text(screen, "#preflight-summary")
        assert "host_generation: fake:fake-v1" in _text(screen, "#llm-preflight")
        assert "Host One: fake-tts / voice-a" in _text(screen, "#tts-preflight")
        assert "FFmpeg: available" in _text(screen, "#ffmpeg-preflight")
        assert "LLM provider 'fake' is unhealthy: offline" in _text(
            screen, "#preflight-issues"
        )
        screen.action_generate()
        await pilot.pause()
        assert "Generation blocked: LLM provider 'fake' is unhealthy: offline" in _text(
            screen, "#screen-status"
        )


class UnhealthyLLM(FakeLLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "offline")


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)),
    )


def _home(app: DeeperDiveApp) -> HomeProjectsScreen:
    assert isinstance(app.screen, HomeProjectsScreen)
    return app.screen


def _sources(app: DeeperDiveApp) -> SourcesScreen:
    assert isinstance(app.screen, SourcesScreen)
    return app.screen


def _preflight(app: DeeperDiveApp) -> PreflightScreen:
    assert isinstance(app.screen, PreflightScreen)
    return app.screen


def _text(screen: HomeProjectsScreen | SourcesScreen | PreflightScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())


def _shortcut(destination: str) -> tuple[str, ...]:
    return {
        "providers": ("p",),
        "settings": ("s",),
        "help": ("?",),
        "sources": ("1",),
        "research": ("2",),
        "hosts": ("3",),
        "episode": ("4",),
        "generate": ("5",),
        "library": ("6",),
    }[destination]
