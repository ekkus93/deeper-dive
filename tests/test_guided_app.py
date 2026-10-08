from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.model_roles import ModelRole
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(WorkspaceManager(tmp_path / "data"))


def _save_ready_config(tmp_path: Path) -> None:
    defaults = {
        ModelRole.EPISODE_PLANNING.value: "fake:fake-v1",
        ModelRole.HOST_GENERATION.value: "fake:fake-v1",
        ModelRole.DIRECTING.value: "fake:fake-v1",
        ModelRole.VERIFICATION.value: "fake:fake-v1",
        "speech_setup": "deferred",
        "quick_deep_dive_duration_minutes": "20",
        "research_policy": "useful",
    }
    UserConfigStore(tmp_path / "data" / "config.json").save(
        UserConfig(
            providers={
                "fake": ProviderConfig(
                    provider_type="fake",
                    default_model="fake-v1",
                    network_scope="local",
                )
            },
            defaults=defaults,
        )
    )


def test_clean_install_routes_to_first_run_setup(tmp_path: Path) -> None:
    asyncio.run(_clean_install_routes_to_first_run_setup(tmp_path))


async def _clean_install_routes_to_first_run_setup(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(_service(tmp_path))

    async with app.run_test(size=(100, 30)):
        assert app.screen.id == "screen-wizard-first-run"


def test_derived_ready_install_skips_automatic_setup(tmp_path: Path) -> None:
    asyncio.run(_derived_ready_install_skips_automatic_setup(tmp_path))


async def _derived_ready_install_skips_automatic_setup(tmp_path: Path) -> None:
    _save_ready_config(tmp_path)
    app = GuidedDeeperDiveApp(_service(tmp_path))

    async with app.run_test(size=(100, 30)):
        assert app.screen.id == "screen-home"


def test_skip_setup_does_not_manufacture_readiness_and_restart_returns_to_setup(
    tmp_path: Path,
) -> None:
    asyncio.run(_skip_setup_does_not_manufacture_readiness(tmp_path))


async def _skip_setup_does_not_manufacture_readiness(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app = GuidedDeeperDiveApp(service)

    async with app.run_test(size=(100, 30)) as pilot:
        assert app.screen.id == "screen-wizard-first-run"
        app.screen.query_one("#setup-skip", Button).press()
        await pilot.pause()
        assert app.screen.id == "screen-home"

    restarted = GuidedDeeperDiveApp(service)
    async with restarted.run_test(size=(100, 30)):
        assert restarted.screen.id == "screen-wizard-first-run"


def test_goal_first_home_exposes_primary_and_advanced_navigation(tmp_path: Path) -> None:
    asyncio.run(_goal_first_home_exposes_navigation(tmp_path))


async def _goal_first_home_exposes_navigation(tmp_path: Path) -> None:
    _save_ready_config(tmp_path)
    service = _service(tmp_path)
    service.create_project("My source research")
    app = GuidedDeeperDiveApp(service)

    async with app.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert app.screen.id == "screen-home"
        primary = tuple(
            button.name
            for button in app.screen.query_one("#global-nav").query(Button)
            if button.display
        )
        assert primary == ("home", "new", "projects", "library")
        advanced = tuple(
            button.name
            for button in app.screen.query_one("#project-nav").query(Button)
            if button.display
        )
        assert advanced == (
            "sources",
            "research",
            "hosts",
            "providers",
            "settings",
            "help",
            "episode",
            "generate",
        )
        assert "My source research" in str(app.screen.query_one("#home-recent-projects").render())
        assert "Setup ready" in str(app.screen.query_one("#home-readiness").render())
        app.screen.query_one("#action-new-deep-dive", Button).press()
        await pilot.pause()
        assert app.screen.id == "screen-wizard-new-deep-dive"


def test_goal_first_home_projects_and_library_routes(tmp_path: Path) -> None:
    asyncio.run(_goal_first_home_projects_and_library_routes(tmp_path))


async def _goal_first_home_projects_and_library_routes(tmp_path: Path) -> None:
    _save_ready_config(tmp_path)
    app = GuidedDeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("library")
        await pilot.pause()
        assert app.screen.id == "screen-library"
        app.action_navigate("projects")
        await pilot.pause()
        assert app.screen.id == "screen-home"
        next(
            button
            for button in app.screen.query_one("#project-nav").query(Button)
            if button.name == "providers" and button.display
        ).press()
        await pilot.pause()
        assert app.screen.id == "screen-providers"


def test_saved_new_deep_dive_resumes_from_durable_project_after_restart(
    tmp_path: Path,
) -> None:
    asyncio.run(_saved_new_deep_dive_resumes_after_restart(tmp_path))


async def _saved_new_deep_dive_resumes_after_restart(tmp_path: Path) -> None:
    _save_ready_config(tmp_path)
    service = _service(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#guided-project-name").value = "Durable Project"
        screen.query_one("#guided-project-topic").value = "Durable source question"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()
        assert screen.context.state.current_step == "sources"
        screen.action_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"

    restarted = GuidedDeeperDiveApp(service)
    async with restarted.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        resume = restarted.screen.query_one("#action-resume-deep-dive", Button)
        assert resume.display
        resume.press()
        await pilot.pause()
        assert restarted.screen.id == "screen-wizard-new-deep-dive"
        assert restarted.screen.context.project_id == project_id
        assert restarted.screen.context.state.current_step == "sources"
        assert restarted.screen.query_one("#guided-source-add-paste", Button).display
        assert not restarted.screen.query_one("#guided-project-create", Button).display


def test_goal_first_home_keyboard_primary_and_advanced_actions(tmp_path: Path) -> None:
    asyncio.run(_goal_first_home_keyboard_primary_and_advanced_actions(tmp_path))


async def _goal_first_home_keyboard_primary_and_advanced_actions(tmp_path: Path) -> None:
    _save_ready_config(tmp_path)
    app = GuidedDeeperDiveApp(_service(tmp_path))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.screen.id == "screen-home"
        library = app.screen.query_one("#guided-nav-library", Button)
        library.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.id == "screen-library"
        app.action_navigate("home")
        await pilot.pause()
        advanced = app.screen.query_one("#guided-nav-providers", Button)
        advanced.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.id == "screen-providers"
