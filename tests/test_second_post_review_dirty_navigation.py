from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def _episode_fixture(
    tmp_path: Path,
) -> tuple[DeeperDiveService, str, str, tuple[str, str]]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Dirty navigation")
    repository = service.hosts(project.id)
    host_ids = ("host-one", "host-two")
    for host_id, name in zip(host_ids, ("Host One", "Host Two"), strict=True):
        repository.create_host(HostProfile(host_id, project.id, name).to_record())
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project.id) / "project.db")
    )
    episode = configs.create(
        project.id,
        EpisodeConfiguration(
            title="Durable title",
            focus="Durable focus",
            target_duration_seconds=1200,
            host_ids=host_ids,
        ),
    )
    return service, project.id, episode.id, host_ids


def test_dirty_episode_back_requires_explicit_discard(tmp_path: Path) -> None:
    asyncio.run(_dirty_episode_back_requires_explicit_discard(tmp_path))


async def _dirty_episode_back_requires_explicit_discard(tmp_path: Path) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_host_order()
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        wizard.query_one("#guided-episode-title", Input).value = "Unsaved title"
        assert not wizard.action_back()
        assert wizard.context.state.current_step == "episode"
        assert wizard.query_one("#guided-episode-title", Input).value == "Unsaved title"
        assert wizard.query_one("#wizard-exit-confirmation").display

        wizard.action_cancel_exit_confirmation()
        assert wizard.context.state.current_step == "episode"
        assert wizard.query_one("#guided-episode-title", Input).value == "Unsaved title"

        wizard.action_back()
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert wizard.context.state.current_step == "hosts"

        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_form()
        assert wizard.query_one("#guided-episode-title", Input).value == "Durable title"


def test_dirty_episode_save_and_back_persists_before_transition(tmp_path: Path) -> None:
    asyncio.run(_dirty_episode_save_and_back_persists_before_transition(tmp_path))


async def _dirty_episode_save_and_back_persists_before_transition(tmp_path: Path) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    configs = EpisodeConfigurationService(app.composition.database_for_project(project_id))
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_host_order()
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        wizard.query_one("#guided-episode-title", Input).value = "Persisted before back"
        wizard.action_back()
        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert wizard.context.state.current_step == "hosts"
        assert configs.load_configuration(episode_id).title == "Persisted before back"


def test_dirty_wizard_global_navigation_uses_same_confirmation(tmp_path: Path) -> None:
    asyncio.run(_dirty_wizard_global_navigation_uses_same_confirmation(tmp_path))


async def _dirty_wizard_global_navigation_uses_same_confirmation(tmp_path: Path) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        wizard.query_one("#guided-episode-focus", Input).value = "Unsaved global-nav edit"
        app.action_navigate("home")
        assert app.screen is wizard
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")

        await pilot.press("space")
        assert app.screen is wizard
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.query_one("#guided-episode-focus", Input).value == "Unsaved global-nav edit"

        app.action_navigate("home")
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"


def test_unsaved_host_order_is_dirty_and_save_exit_persists_order(tmp_path: Path) -> None:
    asyncio.run(_unsaved_host_order_is_dirty_and_save_exit_persists_order(tmp_path))


async def _unsaved_host_order_is_dirty_and_save_exit_persists_order(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    configs = EpisodeConfigurationService(app.composition.database_for_project(project_id))
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._load_episode_host_order()
        wizard._refresh_hosts(host_ids[1])
        wizard._toggle()
        wizard._remember_current_form()

        assert wizard._selected_host_ids == list(host_ids)
        assert not wizard._current_form_dirty()
        wizard._move_selected_host(-1)
        assert wizard._selected_host_ids == [host_ids[1], host_ids[0]]
        assert wizard._current_form_dirty()

        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert app.screen.id == "screen-home"
        assert configs.load_configuration(episode_id).host_ids == (
            host_ids[1],
            host_ids[0],
        )


def test_host_order_move_then_undo_returns_to_clean(tmp_path: Path) -> None:
    asyncio.run(_host_order_move_then_undo_returns_to_clean(tmp_path))


async def _host_order_move_then_undo_returns_to_clean(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._load_episode_host_order()
        wizard._refresh_hosts(host_ids[1])
        wizard._toggle()
        wizard._remember_current_form()

        wizard._move_selected_host(-1)
        assert wizard._current_form_dirty()
        wizard._move_selected_host(1)
        assert wizard._selected_host_ids == list(host_ids)
        assert not wizard._current_form_dirty()
