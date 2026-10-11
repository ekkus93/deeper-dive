from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.preflight import PreflightEstimate, PreflightIssue, PreflightReport
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodePlanRecord
from deeper_dive.storage.workspace import WorkspaceManager


class _TwoSegmentGenerator:
    def generate_plan(self, _request):
        return {
            "segments": [
                {
                    "title": "Opening",
                    "purpose": "Set context",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                },
                {
                    "title": "Deep Dive",
                    "purpose": "Explore evidence",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                },
            ]
        }


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


def test_dirty_plan_segment_blocks_reselection_until_explicit_discard(tmp_path: Path) -> None:
    asyncio.run(_dirty_plan_segment_blocks_reselection_until_explicit_discard(tmp_path))


async def _dirty_plan_segment_blocks_reselection_until_explicit_discard(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    planner = EpisodePlannerService(database, _TwoSegmentGenerator())
    durable = planner.build_plan(episode_id)
    assert len(durable.segments) == 2

    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "plan")
        wizard._plan = planner.load_plan(episode_id)
        wizard._selected_segment_ordinal = 0
        wizard._render_plan()
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        changed = "Unsaved opening title"
        title = wizard.query_one("#guided-plan-title", Input)
        title.value = changed
        await pilot.pause()
        picker = wizard.query_one("#guided-plan-segment-picker", Select)
        picker.value = "1"
        await pilot.pause()

        assert picker.value == "0"
        assert title.value == changed
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")

        wizard.action_cancel_exit_confirmation()
        assert picker.value == "0"
        assert title.value == changed

        picker.value = "1"
        await pilot.pause()
        wizard.action_confirm_discard_exit()
        await pilot.pause()

        assert picker.value == "1"
        assert title.value == durable.segments[1].title
        persisted = planner.load_plan(episode_id)
        assert persisted.segments[0].title == durable.segments[0].title


def test_explicit_discard_restores_form_when_continue_is_still_blocked(
    tmp_path: Path,
) -> None:
    asyncio.run(_discard_restores_blocked_project_form(tmp_path))


async def _discard_restores_blocked_project_form(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard._remember_current_form()

        name = wizard.query_one("#guided-project-name", Input)
        assert name.value == ""
        name.value = "Not saved to the workspace"
        assert not wizard.action_continue()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_discard_exit()
        await pilot.pause()

        assert wizard.context.state.current_step == "project"
        assert name.value == ""
        assert not wizard._current_form_dirty()
        assert service.list_projects() == []


def test_explicit_host_order_discard_reloads_durable_membership(
    tmp_path: Path,
) -> None:
    asyncio.run(_discard_restores_host_membership(tmp_path))


async def _discard_restores_host_membership(tmp_path: Path) -> None:
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
        wizard._refresh_hosts(host_ids[0])
        wizard._toggle()
        wizard._remember_current_form()

        wizard._move_selected_host(1)
        assert wizard._selected_host_ids == [host_ids[1], host_ids[0]]
        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_discard_exit()
        await pilot.pause()

        assert wizard._selected_host_ids == list(host_ids)
        configs = EpisodeConfigurationService(app.composition.database_for_project(project_id))
        assert configs.load_configuration(episode_id).host_ids == host_ids


@pytest.mark.parametrize("decision", ("cancel", "discard", "save", "failed-save"))
def test_recommended_hosts_guard_unsaved_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
) -> None:
    asyncio.run(_recommended_hosts_guard_unsaved_profile(tmp_path, monkeypatch, decision))


async def _recommended_hosts_guard_unsaved_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    repository = service.hosts(project_id)
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

        original = repository.get_host(host_ids[0])
        assert original is not None
        changed = "Instructions not yet saved"
        field = wizard.query_one("#guided-host-instructions", Input)
        field.value = changed
        await pilot.pause()
        wizard.action_create_recommended_hosts()
        wizard.action_create_recommended_hosts()  # repeated click must not bypass modal
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert field.value == changed
        assert len(repository.list_hosts(project_id)) == 2
        assert wizard._selected_host_ids == list(host_ids)

        if decision == "cancel":
            wizard.action_cancel_exit_confirmation()
            await pilot.pause()
            assert field.value == changed
            assert wizard._host_profile_dirty()
            assert len(repository.list_hosts(project_id)) == 2
            return
        if decision == "failed-save":
            monkeypatch.setattr(wizard, "action_save_host", lambda: False)
            wizard.action_confirm_save_exit()
            await pilot.pause()
            assert field.value == changed
            assert wizard._host_profile_dirty()
            assert len(repository.list_hosts(project_id)) == 2
            assert repository.get_host(host_ids[0]).instructions == original.instructions
            return
        if decision == "discard":
            wizard.action_confirm_discard_exit()
        else:
            wizard.action_confirm_save_exit()
        await pilot.pause()
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert len(repository.list_hosts(project_id)) == 4
        assert len(wizard._selected_host_ids) == 4
        persisted = repository.get_host(host_ids[0])
        assert persisted is not None
        assert persisted.instructions == (changed if decision == "save" else original.instructions)
        assert wizard.query_one("#guided-host-instructions", Input).value != changed


def test_host_order_survives_unrelated_refresh_and_app_restart(tmp_path: Path) -> None:
    asyncio.run(_host_order_survives_refresh_and_restart(tmp_path))


async def _host_order_survives_refresh_and_restart(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    expected = [host_ids[1], host_ids[0]]
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

        wizard._move_selected_host(1)
        assert wizard._selected_host_ids == expected
        assert wizard._host_order_dirty()
        wizard._refresh_hosts(host_ids[1])
        await pilot.pause()
        assert wizard._selected_host_ids == expected
        assert wizard._host_order_dirty()
        assert wizard.action_save_host_order()
        assert not wizard._host_order_dirty()

    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    assert configs.load_configuration(episode_id).host_ids == tuple(expected)

    reopened = GuidedDeeperDiveApp(service)
    async with reopened.run_test(size=(100, 35)) as pilot:
        reopened.action_navigate("new")
        await pilot.pause()
        wizard = reopened.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._load_episode_host_order()
        wizard._refresh_hosts(host_ids[0])
        wizard._toggle()
        wizard._remember_current_form()

        assert wizard._selected_host_ids == expected
        assert not wizard._host_order_dirty()


@pytest.mark.parametrize(
    ("step", "selector", "changed"),
    (
        ("provider-config", "#setup-provider-name", "unsaved-provider"),
        ("model-test", "#setup-role-episode-planning", "unsaved:model"),
        ("speech", "#setup-speech-name", "unsaved-speech"),
    ),
)
def test_async_readiness_recovery_preserves_unsaved_setup_edits(
    tmp_path: Path, step: str, selector: str, changed: str
) -> None:
    asyncio.run(
        _async_readiness_recovery_preserves_unsaved_setup_edits(tmp_path, step, selector, changed)
    )


async def _async_readiness_recovery_preserves_unsaved_setup_edits(
    tmp_path: Path, step: str, selector: str, changed: str
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedFirstRunWizard)
        wizard.context.state = WizardState(WizardKind.FIRST_RUN, step)
        wizard._sync_text()
        wizard._sync_setup_controls()
        wizard._remember_current_form()

        field = wizard.query_one(selector, Input)
        original = field.value
        field.value = changed
        assert wizard._current_form_dirty()

        # Simulate a late readiness result invalidating the earliest prerequisite.
        wizard.completion_probe = lambda key: key != "welcome"
        assert wizard.navigator.recovered_state().current_step == "welcome"
        wizard._runtime_readiness_updated()

        assert wizard.context.state.current_step == step
        assert field.value == changed
        assert wizard._current_form_dirty()
        assert "unsaved setup edits remain" in str(
            wizard.query_one("#wizard-status", Static).render()
        )

        # Clean forms may still recover to the now-invalid prerequisite.
        field.value = original
        assert not wizard._current_form_dirty()
        wizard._runtime_readiness_updated()
        assert wizard.context.state.current_step == "welcome"


class _RegenerateAwareGenerator(_TwoSegmentGenerator):
    def generate_plan(self, request):
        if request.get("mode") == "regenerate_segment":
            return {
                "segments": [
                    {
                        "title": "Regenerated opening",
                        "purpose": "Recheck the introductory material",
                        "target_duration_seconds": 600,
                        "questions": [],
                        "evidence_ids": [],
                        "lead_host_ids": [],
                    }
                ]
            }
        return super().generate_plan(request)


@pytest.mark.parametrize("operation", ("build", "regenerate", "regenerate-segment"))
@pytest.mark.parametrize("resolution", ("discard", "save", "invalid-save"))
def test_dirty_plan_operations_require_explicit_save_or_discard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    resolution: str,
) -> None:
    asyncio.run(_dirty_plan_operation(tmp_path, monkeypatch, operation, resolution))


async def _dirty_plan_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, resolution: str
) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    planner = EpisodePlannerService(database, _RegenerateAwareGenerator())
    original = planner.build_plan(episode_id)
    assert len(original.segments) == 2
    saved_titles: list[str] = []
    production_edit = planner.edit_segment

    def record_edit(episode, ordinal, segment):
        saved_titles.append(segment.title)
        return production_edit(episode, ordinal, segment)

    monkeypatch.setattr(planner, "edit_segment", record_edit)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        monkeypatch.setattr(wizard, "_planning_service", lambda: planner)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "plan")
        wizard._plan = planner.load_plan(episode_id)
        wizard._selected_segment_ordinal = 0
        wizard._render_plan()
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        changed = "Do not silently overwrite this draft title"
        title = wizard.query_one("#guided-plan-title", Input)
        title.value = changed
        await pilot.pause()
        actions = {
            "build": wizard.action_build_plan,
            "regenerate": wizard.action_regenerate_plan,
            "regenerate-segment": wizard.action_regenerate_plan_segment,
        }
        invoke = actions[operation]
        invoke()
        invoke()  # duplicate input must not bypass the pending confirmation
        await pilot.pause()

        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")
        assert title.value == changed
        assert planner.load_plan(episode_id).id == original.id
        assert operation.replace("-", " ") in str(
            wizard.query_one("#wizard-status", Static).render()
        ) or "Unsaved changes" in str(wizard.query_one("#wizard-status", Static).render())

        wizard.action_cancel_exit_confirmation()
        await pilot.pause()
        assert title.value == changed
        assert planner.load_plan(episode_id).id == original.id

        if resolution == "invalid-save":
            wizard.query_one("#guided-plan-duration", Input).value = "invalid"
        invoke()
        if resolution == "discard":
            wizard.action_confirm_discard_exit()
        else:
            wizard.action_confirm_save_exit()
            wizard.action_confirm_save_exit()  # double submit is single-shot
        await pilot.pause()
        assert not wizard.query_one("#wizard-exit-confirmation").display
        if resolution == "invalid-save":
            assert saved_titles == []
            assert title.value == changed
            assert planner.load_plan(episode_id).id == original.id
            assert wizard._current_form_dirty()
        else:
            assert planner.load_plan(episode_id).id != original.id
            assert title.value != changed
            assert saved_titles == ([changed] if resolution == "save" else [])


@pytest.mark.parametrize("action", ("generation", "preflight-repair"))
def test_dirty_plan_generation_and_preflight_repair_guard(tmp_path: Path, action: str) -> None:
    asyncio.run(_dirty_plan_entrypoint_guard(tmp_path, action))


async def _dirty_plan_entrypoint_guard(tmp_path: Path, action: str) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    database = Database(service.workspaces.project_root(project_id) / "project.db")
    planner = EpisodePlannerService(database, _TwoSegmentGenerator())
    plan = planner.build_plan(episode_id)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project_id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "plan")
        wizard._plan = planner.load_plan(episode_id)
        wizard._render_plan()
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()
        wizard._preflight = PreflightReport(
            (PreflightIssue("sources_missing", "Index sources"),),
            PreflightEstimate(20, 0, 0, None),
        )
        title = wizard.query_one("#guided-plan-title", Input)
        title.value = "Unsaved plan edit before starting generation"
        await pilot.pause()

        if action == "generation":
            wizard.action_generate_deep_dive()
        else:
            wizard.action_fix_preflight()
        await pilot.pause()

        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")
        assert wizard.context.state.current_step == "plan"
        assert title.value == "Unsaved plan edit before starting generation"
        assert planner.load_plan(episode_id).id == plan.id
        assert wizard.context.run_id is None

        wizard.action_cancel_exit_confirmation()
        await pilot.pause()
        assert wizard.context.state.current_step == "plan"
        assert title.value == "Unsaved plan edit before starting generation"
        assert not wizard.query_one("#wizard-exit-confirmation").display


def test_guided_noop_save_keeps_exact_non_minute_duration_and_plan(tmp_path: Path) -> None:
    asyncio.run(_guided_noop_save_keeps_exact_non_minute_duration_and_plan(tmp_path))


async def _guided_noop_save_keeps_exact_non_minute_duration_and_plan(tmp_path: Path) -> None:
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
    repository = service.hosts(project_id)
    repository.save_plan(
        EpisodePlanRecord(
            id="non-minute-duration-plan",
            episode_id=episode_id,
            created_at="now",
            modified_at="now",
        ),
        [],
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
        assert wizard.action_save_episode()
        assert configs.load_configuration(episode_id).target_duration_seconds == 1250
        assert repository.get_plan(episode_id) is not None
        assert repository.get_plan(episode_id).id == "non-minute-duration-plan"

        # An explicit duration edit still changes the durable configuration
        # and invalidates the old plan through EpisodeConfigurationService.
        custom.value = "22"
        assert wizard.action_save_episode()
        assert configs.load_configuration(episode_id).target_duration_seconds == 1320
        assert repository.get_plan(episode_id) is None


def test_host_membership_add_remove_and_target_identity_dirty_contract(tmp_path: Path) -> None:
    asyncio.run(_host_membership_add_remove_and_target_identity_dirty_contract(tmp_path))


async def _host_membership_add_remove_and_target_identity_dirty_contract(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    repository = service.hosts(project_id)
    repository.create_host(HostProfile("third-host", project_id, "Third Host").to_record())
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    other = configs.create(
        project_id, EpisodeConfiguration(title="Other episode", host_ids=host_ids)
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
        wizard._refresh_hosts("third-host")
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        assert not wizard._current_form_dirty()
        wizard.action_select_host()
        assert wizard._selected_host_ids == [*host_ids, "third-host"]
        assert wizard._host_order_dirty()
        wizard.action_remove_selected_host()
        assert wizard._selected_host_ids == list(host_ids)
        assert not wizard._current_form_dirty()

        wizard._refresh_hosts(host_ids[1])
        await pilot.pause()
        wizard._remember_current_form()
        wizard.action_remove_selected_host()
        assert wizard._host_order_dirty()
        wizard.action_select_host()
        assert wizard._selected_host_ids == list(host_ids)
        assert not wizard._host_order_dirty()

        wizard._refresh_hosts(host_ids[0])
        await pilot.pause()
        wizard._remember_current_form()
        wizard._move_selected_host(-1)
        assert not wizard._host_order_dirty()

        # Identical host IDs in a different episode are a different dirty target.
        wizard.context.episode_id = other.id
        assert wizard._host_order_dirty()
        wizard.context.episode_id = episode_id
        assert not wizard._host_order_dirty()
        assert configs.load_configuration(episode_id).host_ids == host_ids
        assert configs.load_configuration(other.id).host_ids == host_ids


def test_host_refresh_preserves_dirty_profile_and_selected_identity(tmp_path: Path) -> None:
    asyncio.run(_host_refresh_preserves_dirty_profile_and_selected_identity(tmp_path))


async def _host_refresh_preserves_dirty_profile_and_selected_identity(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    repository = service.hosts(project_id)
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

        field = wizard.query_one("#guided-host-instructions", Input)
        field.value = "Unsaved instructions must survive host list refresh"
        await pilot.pause()
        assert wizard._host_profile_dirty()
        wizard._refresh_hosts(host_ids[1])
        await pilot.pause()

        assert wizard.query_one("#guided-host-picker", Select).value == host_ids[0]
        assert wizard._loaded_host_id == host_ids[0]
        assert field.value == "Unsaved instructions must survive host list refresh"
        assert wizard._host_profile_dirty()
        assert wizard._current_form_dirty()
        durable = repository.get_host(host_ids[0])
        assert durable is not None and durable.instructions != field.value

        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_cancel_exit_confirmation()
        assert field.value == "Unsaved instructions must survive host list refresh"


def test_explicit_host_save_rehydrates_normalized_durable_values(tmp_path: Path) -> None:
    asyncio.run(_explicit_host_save_rehydrates_normalized_durable_values(tmp_path))


async def _explicit_host_save_rehydrates_normalized_durable_values(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    repository = service.hosts(project_id)
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

        field = wizard.query_one("#guided-host-instructions", Input)
        field.value = "  Normalized durable instructions  "
        await pilot.pause()
        assert wizard._host_profile_dirty()
        assert wizard.action_save_host()
        await pilot.pause()

        durable = repository.get_host(host_ids[0])
        assert durable is not None
        assert durable.instructions == "Normalized durable instructions"
        assert field.value == durable.instructions
        assert not wizard._host_profile_dirty()
        assert not wizard._current_form_dirty()


def test_combined_host_profile_and_membership_save_is_durable_and_single_shot(
    tmp_path: Path,
) -> None:
    asyncio.run(_combined_host_profile_and_membership_save(tmp_path))


async def _combined_host_profile_and_membership_save(tmp_path: Path) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    repository = service.hosts(project_id)
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

        wizard.query_one(
            "#guided-host-instructions", Input
        ).value = "Durable profile and membership update"
        wizard._move_selected_host(1)
        assert wizard._host_profile_dirty()
        assert wizard._host_order_dirty()

        wizard.action_save_exit()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_save_exit()
        wizard.action_confirm_save_exit()  # repeated activation cannot save twice
        await pilot.pause()
        assert app.screen.id == "screen-home"

    persisted = repository.get_host(host_ids[0])
    assert persisted is not None
    assert persisted.instructions == "Durable profile and membership update"
    reopened = DeeperDiveService(WorkspaceManager(service.workspaces.data_dir))
    config = EpisodeConfigurationService(
        Database(reopened.workspaces.project_root(project_id) / "project.db")
    ).load_configuration(episode_id)
    assert config.host_ids == (host_ids[1], host_ids[0])


def test_combined_host_save_isolated_across_episodes_and_projects(tmp_path: Path) -> None:
    asyncio.run(_combined_host_save_isolated_across_episodes_and_projects(tmp_path))


async def _combined_host_save_isolated_across_episodes_and_projects(
    tmp_path: Path,
) -> None:
    service, project_id, episode_id, host_ids = _episode_fixture(tmp_path)
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project_id) / "project.db")
    )
    sibling = configs.create(
        project_id, EpisodeConfiguration(title="Sibling episode", host_ids=host_ids)
    )
    foreign = service.create_project("Isolated project")
    foreign_hosts = service.hosts(foreign.id)
    for host_id in host_ids:
        foreign_hosts.create_host(
            HostProfile(host_id, foreign.id, f"Foreign {host_id}").to_record()
        )
    foreign_configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(foreign.id) / "project.db")
    )
    foreign_episode = foreign_configs.create(
        foreign.id,
        EpisodeConfiguration(title="Foreign episode", host_ids=host_ids),
    )
    foreign_original = foreign_hosts.get_host(host_ids[0])
    assert foreign_original is not None

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
        wizard.query_one("#guided-host-instructions", Input).value = "Project A only profile update"
        wizard._move_selected_host(1)
        assert wizard._host_profile_dirty() and wizard._host_order_dirty()
        wizard.action_save_exit()
        wizard.action_confirm_save_exit()
        await pilot.pause()

    assert configs.load_configuration(episode_id).host_ids == tuple(reversed(host_ids))
    assert configs.load_configuration(sibling.id).host_ids == host_ids
    updated = service.hosts(project_id).get_host(host_ids[0])
    assert updated is not None and updated.instructions == "Project A only profile update"
    assert foreign_configs.load_configuration(foreign_episode.id).host_ids == host_ids
    assert foreign_hosts.get_host(host_ids[0]) == foreign_original


def test_completed_episode_edit_guides_user_to_create_new_episode_without_plan_loss(
    tmp_path: Path,
) -> None:
    asyncio.run(_completed_episode_edit_requires_new_episode(tmp_path))


async def _completed_episode_edit_requires_new_episode(tmp_path: Path) -> None:
    service, project_id, episode_id, _host_ids = _episode_fixture(tmp_path)
    db = Database(service.workspaces.project_root(project_id) / "project.db")
    configs = EpisodeConfigurationService(db)
    repository = service.hosts(project_id)
    repository.save_plan(
        EpisodePlanRecord(
            id="completed-immutable-plan",
            episode_id=episode_id,
            created_at="now",
            modified_at="now",
        ),
        [],
    )
    with db.transaction(immediate=True) as connection:
        connection.execute("UPDATE episodes SET state='completed' WHERE id=?", (episode_id,))
    before = configs.load_configuration(episode_id)
    before_plan = repository.get_plan(episode_id)
    assert before_plan is not None

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

        focus = wizard.query_one("#guided-episode-focus", Input)
        focus.value = "Unsaved change to completed episode"
        assert not wizard.action_save_episode()
        await pilot.pause()

        guidance = str(wizard.query_one("#guided-episode-validation", Static).render())
        assert "create a new episode" in guidance
        assert wizard.context.episode_id == episode_id
        assert wizard.context.state.current_step == "episode"
        assert focus.value == "Unsaved change to completed episode"
        assert wizard._current_form_dirty()
        assert configs.load_configuration(episode_id) == before
        saved_episode = repository.get_episode(episode_id)
        assert saved_episode is not None and saved_episode.state == "completed"
        assert repository.get_plan(episode_id) == before_plan
