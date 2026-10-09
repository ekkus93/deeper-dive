"""Extended Textual Save/Exit matrix for every New Deep Dive editable surface."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.workspace import WorkspaceManager


def test_dirty_file_and_url_inputs_survive_failed_save_exit(tmp_path: Path) -> None:
    asyncio.run(_dirty_source_inputs_survive(tmp_path))


async def _dirty_source_inputs_survive(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Source Save Exit")
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "sources")
        wizard._toggle()
        wizard._refresh_sources()
        wizard._remember_current_form()

        missing = str(tmp_path / "does-not-exist.md")
        wizard.query_one("#guided-source-paths", Input).value = missing
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()
        assert app.screen is wizard
        assert wizard.query_one("#guided-source-paths", Input).value == missing
        assert not service.list_sources(project.id)

        wizard.query_one("#guided-source-paths", Input).value = ""
        wizard.query_one("#guided-source-urls", Input).value = ""
        wizard._remember_current_form()
        invalid_url = "ftp://example.invalid/private"
        wizard.query_one("#guided-source-urls", Input).value = invalid_url
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()
        assert app.screen is wizard
        assert wizard.query_one("#guided-source-urls", Input).value == invalid_url
        assert not service.list_sources(project.id)


def test_dirty_host_cancel_retains_input_and_durable_host(tmp_path: Path) -> None:
    asyncio.run(_dirty_host_cancel_retains_input(tmp_path))


async def _dirty_host_cancel_retains_input(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Host Save Exit")
    repository = service.hosts(project.id)
    host = HostProfile(
        id="host-save-exit",
        project_id=project.id,
        display_name="Durable Host",
        role="Durable role",
        instructions="Durable instructions",
    )
    repository.create_host(host.to_record())
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._refresh_hosts(host.id)
        wizard._toggle()
        wizard._remember_current_form()

        changed = "Unsaved host instructions"
        wizard.query_one("#guided-host-instructions", Input).value = changed
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_cancel_exit_confirmation()
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.query_one("#guided-host-instructions", Input).value == changed
        durable = repository.get_host(host.id)
        assert durable is not None
        assert durable.instructions == "Durable instructions"


def test_invalid_dirty_episode_save_retains_input_and_durable_config(tmp_path: Path) -> None:
    asyncio.run(_invalid_episode_save_retains_input(tmp_path))


async def _invalid_episode_save_retains_input(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Episode Save Exit")
    repository = service.hosts(project.id)
    host = HostProfile("episode-host", project.id, "Episode Host")
    repository.create_host(host.to_record())
    configs = EpisodeConfigurationService(service.database_for_project(project.id))
    episode = configs.create(
        project.id,
        EpisodeConfiguration(
            title="Durable Episode",
            focus="Durable focus",
            audience="general",
            target_duration_seconds=1200,
            host_ids=(host.id,),
        ),
    )

    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_form()
        wizard._toggle()
        wizard._remember_current_form()

        wizard.query_one("#guided-episode-title", Input).value = ""
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()
        assert app.screen is wizard
        assert wizard.query_one("#guided-episode-title", Input).value == ""
        assert "Fix episode settings" in str(
            wizard.query_one("#guided-episode-validation", Static).render()
        )
        assert configs.load_configuration(episode.id).title == "Durable Episode"
