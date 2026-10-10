from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
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
        await pilot.pause()
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


def test_dirty_host_profile_blocks_picker_reselection_until_discard(tmp_path: Path) -> None:
    asyncio.run(_dirty_host_profile_blocks_picker_reselection_until_discard(tmp_path))


async def _dirty_host_profile_blocks_picker_reselection_until_discard(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    repository = service.hosts(project_id)
    first = repository.get_host(host_ids[0])
    second = repository.get_host(host_ids[1])
    assert first is not None and second is not None
    repository.update_host(HostProfile.from_record(first).to_record())
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
        wizard._refresh_hosts(host_ids[0])
        wizard._toggle()
        wizard._remember_current_form()

        changed = "Unsaved instructions stay visible"
        wizard.query_one("#guided-host-instructions", Input).value = changed
        # Yield exactly as real keyboard input does so Input.Changed records the
        # durable-target edit before the user can activate another Select option.
        await pilot.pause()
        picker = wizard.query_one("#guided-host-picker", Select)
        picker.value = host_ids[1]
        await pilot.pause()

        assert picker.value == host_ids[0]
        assert wizard.query_one("#guided-host-instructions", Input).value == changed
        assert wizard.query_one("#wizard-exit-confirmation").display

        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert picker.value == host_ids[1]
        assert wizard.query_one("#guided-host-instructions", Input).value == second.instructions
        durable_first = repository.get_host(host_ids[0])
        assert durable_first is not None
        assert durable_first.instructions != changed


def test_partial_file_import_retains_unresolved_input_on_save_exit(tmp_path: Path) -> None:
    asyncio.run(_partial_file_import_retains_unresolved_input_on_save_exit(tmp_path))


async def _partial_file_import_retains_unresolved_input_on_save_exit(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Mixed source input")
    good = tmp_path / "good.md"
    good.write_text("Durable evidence from the supported file.", encoding="utf-8")
    unsupported = tmp_path / "unsupported.bin"
    unsupported.write_bytes(b"not a supported source")
    app = GuidedDeeperDiveApp(service)

    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "sources")
        wizard._refresh_sources()
        wizard._toggle()
        wizard._remember_current_form()

        field = wizard.query_one("#guided-source-paths", Input)
        field.value = f"{good},{unsupported}"
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert app.screen is wizard
        assert field.value == str(unsupported)
        imported = service.list_sources(project.id)
        assert len(imported) == 1
        assert imported[0].locator == str(good)
        assert "unresolved input(s) retained" in str(wizard.query_one("#wizard-status").render())


def test_dirty_episode_screen_resume_preserves_typed_values(tmp_path: Path) -> None:
    asyncio.run(_dirty_episode_screen_resume_preserves_typed_values(tmp_path))


async def _dirty_episode_screen_resume_preserves_typed_values(tmp_path: Path) -> None:
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

        changed = "Unsaved focus must survive screen resume"
        wizard.query_one("#guided-episode-focus", Input).value = changed
        wizard.on_screen_resume()
        await pilot.pause()

        assert wizard.context.state.current_step == "episode"
        assert wizard.query_one("#guided-episode-focus", Input).value == changed
        assert "Unsaved changes remain" in str(wizard.query_one("#wizard-status", Static).render())


def test_first_run_dirty_guard_covers_each_editable_stage(tmp_path: Path) -> None:
    asyncio.run(_first_run_dirty_guard_covers_each_editable_stage(tmp_path))


async def _first_run_dirty_guard_covers_each_editable_stage(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)

        cases = (
            ("provider-config", "#setup-provider-name", "dirty-provider"),
            ("model-test", "#setup-role-episode-planning", "dirty:model"),
            ("speech", "#setup-speech-name", "dirty-speech"),
        )
        for step, selector, changed in cases:
            wizard.context.state = WizardState(WizardKind.FIRST_RUN, step)
            wizard._sync_text()
            wizard._sync_setup_controls()
            wizard._remember_current_form()
            field = wizard.query_one(selector, Input)
            field.value = changed

            assert not wizard.action_back()
            assert wizard.context.state.current_step == step
            assert field.value == changed
            assert wizard.query_one("#wizard-exit-confirmation").display
            wizard.action_cancel_exit_confirmation()
            assert field.value == changed

            field.value = ""
            wizard._remember_current_form()

        wizard.context.state = WizardState(WizardKind.FIRST_RUN, "voice-defaults")
        wizard._sync_text()
        wizard._sync_setup_controls()
        wizard._remember_current_form()
        duration = wizard.query_one("#setup-duration", Select)
        original = duration.value
        duration.value = "30" if original != "30" else "20"

        assert not wizard.action_back()
        assert wizard.context.state.current_step == "voice-defaults"
        assert duration.value != original
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_cancel_exit_confirmation()


def test_mixed_host_profile_order_failure_keeps_only_unsaved_order_dirty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_mixed_host_profile_order_failure(tmp_path, monkeypatch))


async def _mixed_host_profile_order_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    configs = EpisodeConfigurationService(app.composition.database_for_project(project_id))
    repository = service.hosts(project_id)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._load_episode_host_order()
        wizard._refresh_hosts(host_ids[0])
        wizard._toggle()
        wizard._remember_current_form()

        changed = "Durable profile half"
        wizard.query_one("#guided-host-instructions", Input).value = changed
        wizard._move_selected_host(1)
        assert wizard._host_profile_dirty()
        assert wizard._host_order_dirty()

        monkeypatch.setattr(wizard, "action_save_host_order", lambda: False)
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert app.screen is wizard
        durable = repository.get_host(host_ids[0])
        assert durable is not None and durable.instructions == changed
        assert configs.load_configuration(episode_id).host_ids == host_ids
        assert not wizard._host_profile_dirty()
        assert wizard._host_order_dirty()
        assert "membership/order was not" in str(
            wizard.query_one("#wizard-status", Static).render()
        )


def test_duplicate_save_confirmation_cannot_create_or_navigate_twice(tmp_path: Path) -> None:
    asyncio.run(_duplicate_save_confirmation_cannot_create_or_navigate_twice(tmp_path))


async def _duplicate_save_confirmation_cannot_create_or_navigate_twice(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.query_one("#guided-project-name", Input).value = "Only once"
        wizard.query_one("#guided-project-topic", Input).value = "Duplicate-submit guard"

        assert not wizard.action_continue()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert wizard.context.state.current_step == "sources"
        projects = service.list_projects()
        assert len(projects) == 1
        assert projects[0].name == "Only once"
