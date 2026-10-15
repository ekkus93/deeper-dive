from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from dirty_navigation_support import _episode_fixture
from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import Transition, TransitionKind


@pytest.mark.parametrize("first_run", (True, False))
def test_escape_dirty_confirmation_cancels_transition_without_losing_edits(
    tmp_path: Path, first_run: bool
) -> None:
    asyncio.run(_escape_dirty_confirmation_cancels_transition(tmp_path, first_run))


async def _escape_dirty_confirmation_cancels_transition(tmp_path: Path, first_run: bool) -> None:
    """Keyboard Escape cancels a dirty confirmation, never silently discards."""
    if first_run:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    else:
        service, project_id, episode_id, _hosts = _episode_fixture(tmp_path)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        if first_run:
            await pilot.pause()
            wizard = app.screen
            assert isinstance(wizard, GuidedFirstRunWizard)
            wizard.context.state = WizardState(WizardKind.FIRST_RUN, "provider-config")
            wizard._sync_text()
            wizard._sync_setup_controls()
            selector = "#setup-provider-name"
        else:
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
            selector = "#guided-episode-title"

        wizard._remember_current_form()
        input_widget = wizard.query_one(selector, Input)
        input_widget.value = "Pending Escape edit"
        assert wizard._current_form_dirty()
        assert wizard.action_back() is False
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")

        await pilot.press("escape")
        await pilot.pause()

        assert app.screen is wizard
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert input_widget.value == "Pending Escape edit"
        assert wizard._current_form_dirty()
        if first_run:
            assert wizard.context.state.current_step == "provider-config"
        else:
            assert wizard.context.state.current_step == "episode"
            config = EpisodeConfigurationService(
                app.composition.database_for_project(project_id)
            ).load_configuration(episode_id)
            assert config.title == "Durable title"

        await pilot.press("escape")
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert input_widget.value == "Pending Escape edit"
        wizard.action_cancel_exit_confirmation()


def test_concurrent_episode_update_cannot_be_overwritten_by_stale_guided_form(
    tmp_path: Path,
) -> None:
    asyncio.run(_stale_guided_episode_save_is_rejected(tmp_path))


async def _stale_guided_episode_save_is_rejected(tmp_path: Path) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    external = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    sibling = external.create(project_id, EpisodeConfiguration(title="Independent episode"))
    original_sibling = service.hosts(project_id).get_episode(sibling.id)
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

        # The user is editing a stale copy while a second production client saves.
        title = wizard.query_one("#guided-episode-title", Input)
        title.value = "Unsaved title from first writer"
        externally_saved = external.load_configuration(episode_id)
        external.edit(
            episode_id,
            EpisodeConfiguration(
                **{**externally_saved.snapshot(), "focus": "Updated by other writer"}
            ),
        )
        assert not wizard.action_save_episode()
        assert "changed since this form was loaded" in str(
            wizard.query_one("#guided-episode-validation", Static).render()
        )
        assert title.value == "Unsaved title from first writer"
        assert wizard.context.state.current_step == "episode"
        assert wizard._current_form_dirty()
        latest = external.load_configuration(episode_id)
        assert latest.title == "Durable title"
        assert latest.focus == "Updated by other writer"
        assert service.hosts(project_id).get_episode(sibling.id) == original_sibling

        # An intentional fresh load acknowledges the remote edit; a subsequent
        # production save must preserve the other writer's unrelated focus.
        wizard._load_episode_form()
        wizard._remember_current_form()
        assert title.value == "Durable title"
        assert wizard.query_one("#guided-episode-focus", Input).value == latest.focus
        title.value = "New title after explicit reload"
        assert wizard.action_save_episode()
        saved = external.load_configuration(episode_id)
        assert saved.title == "New title after explicit reload"
        assert saved.focus == "Updated by other writer"
        assert service.hosts(project_id).get_episode(sibling.id) == original_sibling


def test_concurrent_host_edit_rejects_stale_guided_profile_and_preserves_input(
    tmp_path: Path,
) -> None:
    asyncio.run(_stale_guided_host_save_is_rejected(tmp_path))


async def _stale_guided_host_save_is_rejected(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    external = HostEpisodeRepository(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
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

        instructions = wizard.query_one("#guided-host-instructions", Input)
        instructions.value = "Pending instructions from first editor"
        durable = external.get_host(host_ids[0])
        assert durable is not None
        external.update_host(replace(durable, role="Role from the other editor"))
        assert not wizard.action_save_host()
        assert instructions.value == "Pending instructions from first editor"
        assert wizard._host_profile_dirty()
        actual = external.get_host(host_ids[0])
        assert actual is not None
        assert actual.role == "Role from the other editor"
        assert actual.instructions == durable.instructions

        # A second write raced after any UI precheck: SQLite's expected-row
        # predicate rejects it rather than losing the newer durable data.
        with pytest.raises(ValueError, match="changed concurrently"):
            external.update_host(
                replace(durable, instructions="would erase newer role"),
                expected_host=durable,
            )
        assert external.get_host(host_ids[0]) == actual

        wizard._refresh_hosts(host_ids[0], preserve_dirty=False)
        wizard._remember_host_profile_baseline()
        assert wizard.query_one("#guided-host-role", Input).value == actual.role
        instructions.value = "New instructions after deliberate reload"
        assert wizard.action_save_host()
        saved = external.get_host(host_ids[0])
        assert saved is not None
        assert saved.role == actual.role
        assert saved.instructions == "New instructions after deliberate reload"
        assert external.get_host(host_ids[1]) is not None
        assert tuple(service.hosts(project_id).list_episode_host_ids(episode_id)) == host_ids


def test_hidden_custom_duration_edits_are_guarded_across_back_and_explicit_discard(
    tmp_path: Path,
) -> None:
    asyncio.run(_guard_hidden_custom_duration(tmp_path))


async def _guard_hidden_custom_duration(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    configs.edit(
        episode_id,
        EpisodeConfiguration(
            title="Durable title",
            focus="Durable focus",
            target_duration_seconds=1250,
            host_ids=host_ids,
        ),
    )
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

        assert wizard.query_one("#guided-episode-duration", Select).value == "custom"
        custom = wizard.query_one("#guided-episode-custom-duration", Input)
        assert custom.value == "21"
        custom.value = "25"
        assert wizard._current_form_dirty()
        assert not wizard.action_back()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert custom.value == "25"
        wizard.action_cancel_exit_confirmation()
        assert custom.value == "25"
        assert wizard._current_form_dirty()

        assert not wizard.action_back()
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        assert wizard.context.state.current_step == "hosts"
        assert configs.load_configuration(episode_id).target_duration_seconds == 1250
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
        wizard._load_episode_form()
        assert custom.value == "21"


def test_failed_episode_storage_write_keeps_dirty_fields_and_current_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asyncio.run(_failed_episode_storage_write_keeps_form(tmp_path, monkeypatch))


async def _failed_episode_storage_write_keeps_form(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, project_id, episode_id, _hosts = _episode_fixture(tmp_path)
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
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

        original_edit = EpisodeConfigurationService.edit

        def storage_failure(
            self: EpisodeConfigurationService,
            episode_id: str,
            config: EpisodeConfiguration,
            **_: object,
        ) -> object:
            raise OSError("simulated database filesystem failure")

        monkeypatch.setattr(EpisodeConfigurationService, "edit", storage_failure)
        title = wizard.query_one("#guided-episode-title", Input)
        title.value = "Keep this title after simulated write failure"
        assert not wizard.action_continue()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        await pilot.pause()

        assert wizard.context.state.current_step == "episode"
        assert wizard.context.episode_id == episode_id
        assert title.value == "Keep this title after simulated write failure"
        assert wizard._current_form_dirty()
        assert configs.load_configuration(episode_id).title == "Durable title"
        assert not wizard.query_one("#wizard-exit-confirmation").display

        # A second deliberate save through the normal production service
        # succeeds without losing the previous input.
        monkeypatch.setattr(EpisodeConfigurationService, "edit", original_edit)
        assert wizard.action_save_episode()
        assert configs.load_configuration(episode_id).title == title.value


def test_stale_guided_host_order_does_not_replace_other_editor_membership(
    tmp_path: Path,
) -> None:
    asyncio.run(_stale_host_order_requires_reload(tmp_path))


async def _stale_host_order_requires_reload(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    external = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
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

        # Another production client updates the membership after hydration.
        externally_saved = external.load_configuration(episode_id)
        external.edit(
            episode_id,
            replace(externally_saved, host_ids=tuple(reversed(host_ids))),
        )
        wizard._selected_host_ids = [host_ids[0]]
        assert wizard._host_order_dirty()
        assert not wizard.action_save_host_order()
        assert wizard._selected_host_ids == [host_ids[0]]
        assert external.load_configuration(episode_id).host_ids == tuple(reversed(host_ids))
        assert "changed since this form was loaded" in str(
            wizard.query_one("#wizard-status", Static).render()
        )

        # Only an explicit refresh adopts the other writer's new baseline.
        wizard._load_episode_host_order()
        wizard._refresh_host_order()
        wizard._remember_current_form()
        assert wizard._selected_host_ids == list(reversed(host_ids))
        wizard._selected_host_ids = list(host_ids)
        assert wizard.action_save_host_order()
        assert external.load_configuration(episode_id).host_ids == host_ids


def test_clean_first_run_back_continue_and_escape_do_not_request_discard(
    tmp_path: Path,
) -> None:
    asyncio.run(_clean_first_run_navigation(tmp_path))


async def _clean_first_run_navigation(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        assert wizard.context.state.current_step == "welcome"
        assert wizard.action_continue()
        assert wizard.context.state.current_step == "system-check"
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.action_back()
        assert wizard.context.state.current_step == "welcome"
        assert not wizard.query_one("#wizard-exit-confirmation").display
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "screen-home"
        assert not wizard.query_one("#wizard-exit-confirmation").display


def test_switching_source_details_never_replaces_unsaved_import_fields(
    tmp_path: Path,
) -> None:
    asyncio.run(_source_picker_preserves_unsaved_import_fields(tmp_path))


async def _source_picker_preserves_unsaved_import_fields(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Independent source forms")
    a = service.add_pasted_source(project.id, "A", "Evidence about the first source.")
    b = service.add_pasted_source(project.id, "B", "Evidence about the second source.")
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "sources")
        wizard._refresh_sources(a.id)
        wizard._toggle()
        wizard._remember_current_form()

        title = wizard.query_one("#guided-source-title", Input)
        body = wizard.query_one("#guided-source-text", Input)
        title.value = "An unfinished source title"
        body.value = "Unsaved source text that must not be replaced."
        wizard.query_one("#guided-source-picker", Select).value = b.id
        await pilot.pause()
        assert title.value == "An unfinished source title"
        assert body.value == "Unsaved source text that must not be replaced."
        assert wizard._current_form_dirty()
        assert not wizard.action_back()
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert len(service.list_sources(project.id)) == 2
        wizard.action_cancel_exit_confirmation()
        assert body.value == "Unsaved source text that must not be replaced."


def test_shared_typed_dirty_snapshot_carries_target_values_and_intended_destination(
    tmp_path: Path,
) -> None:
    asyncio.run(_typed_dirty_snapshot_preserves_target(tmp_path))


async def _typed_dirty_snapshot_preserves_target(tmp_path: Path) -> None:
    service, project_id, episode_id, _hosts = _episode_fixture(tmp_path)
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
        clean = wizard._dirty_form_snapshot()
        assert clean.target_identity == (project_id, episode_id, episode_id)
        assert clean.baseline_identity == clean.target_identity
        assert clean.durable_baseline == clean.displayed_values
        assert not clean.dirty
        assert clean.original_destination is None

        title = wizard.query_one("#guided-episode-title", Input)
        title.value = "  Unsaved episode title  "
        pending = wizard._dirty_form_snapshot()
        assert pending.dirty
        assert ("guided-episode-title", "  Unsaved episode title  ") in pending.displayed_values
        assert ("guided-episode-title", "Unsaved episode title") in pending.semantic_snapshot
        assert not wizard.action_back()
        pending = wizard._dirty_form_snapshot()
        assert pending.original_destination == Transition(TransitionKind.BACK)
        assert pending.target_identity == clean.target_identity
        assert pending.durable_baseline == clean.durable_baseline
        wizard.action_cancel_exit_confirmation()
        assert wizard._dirty_form_snapshot().dirty

        # Switching to a different underlying episode without rehydrating
        # must never make the old screen's baseline appear clean.
        another = EpisodeConfigurationService(
            Database(service.workspaces.project_root(project_id) / "project.db")
        ).create(project_id, EpisodeConfiguration(title="Independent target"))
        wizard.context.episode_id = another.id
        title.value = "Durable title"
        switched = wizard._dirty_form_snapshot()
        assert switched.target_identity[1] == another.id
        assert switched.dirty
