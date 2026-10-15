"""TPR-06: Discard is scoped to the dirty area that raised the prompt."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest.mock import patch

from textual.pilot import Pilot
from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import TransitionKind

Scenario = Callable[[GuidedEpisodeWizard, Pilot, DeeperDiveService, str], Awaitable[None]]


async def _run(tmp_path: Path, scenario: Scenario, *, with_episode: bool) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Host discard scope")
    repository = service.hosts(project.id)
    for host_id in ("first", "second"):
        repository.create_host(HostProfile(host_id, project.id, host_id).to_record())
    episode_id: str | None = None
    if with_episode:
        db = Database(service.workspaces.project_root(project.id) / "project.db")
        episode_id = (
            EpisodeConfigurationService(db)
            .create(project.id, EpisodeConfiguration(title="E", host_ids=("first", "second")))
            .id
        )
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode_id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        if with_episode:
            wizard._load_episode_host_order()
        else:
            wizard._selected_host_ids = ["first", "second"]
        wizard._refresh_hosts("first")
        wizard._toggle()
        wizard._remember_current_form()
        await pilot.pause()
        await scenario(wizard, pilot, service, project.id)


def _status(wizard: GuidedEpisodeWizard) -> str:
    return str(wizard.query_one("#wizard-status", Static).render())


async def _profile_discard_keeps_order(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    instructions = wizard.query_one("#guided-host-instructions", Input)
    original = instructions.value
    instructions.value = "Unsaved profile edit"
    wizard._move_selected_host(1)
    assert wizard._selected_host_ids == ["second", "first"]

    wizard.query_one("#guided-host-picker", Select).value = "second"
    await pilot.pause()
    assert wizard._exit_confirmation_pending
    assert wizard._pending_transition is not None
    assert wizard._pending_transition.kind is TransitionKind.HOST_SELECT
    assert "host profile only" in _status(wizard)

    wizard.action_confirm_discard_exit()
    await pilot.pause()

    assert wizard._selected_host_ids == ["second", "first"]
    assert wizard._host_order_dirty()
    assert not wizard._host_profile_dirty()
    assert wizard.query_one("#guided-host-instructions", Input).value != "Unsaved profile edit"
    assert original != "Unsaved profile edit"


async def _leave_step_discard_reverts_both(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    wizard.query_one("#guided-host-instructions", Input).value = "Unsaved profile edit"
    wizard._move_selected_host(1)
    wizard.action_back()
    await pilot.pause()
    assert wizard._exit_confirmation_pending
    assert "both the host profile and the episode host order" in _status(wizard)

    wizard.action_confirm_discard_exit()
    await pilot.pause()

    assert wizard._selected_host_ids == ["first", "second"]
    assert wizard.query_one("#guided-host-instructions", Input).value != "Unsaved profile edit"


async def _no_episode_profile_discard_keeps_selection(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    wizard._selected_host_ids = ["first"]
    wizard._refresh_host_order()
    wizard.query_one("#guided-host-instructions", Input).value = "Unsaved profile edit"
    wizard.query_one("#guided-host-picker", Select).value = "second"
    await pilot.pause()
    assert wizard._exit_confirmation_pending

    wizard.action_confirm_discard_exit()
    await pilot.pause()

    assert wizard._selected_host_ids == ["first"]


async def _no_episode_leave_step_restores_entry_selection(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    wizard._selected_host_ids = ["first"]
    wizard._refresh_host_order()
    wizard.action_back()
    await pilot.pause()
    assert wizard._exit_confirmation_pending

    wizard.action_confirm_discard_exit()
    await pilot.pause()

    # Not "empty": the step-entry in-memory selection comes back.
    assert wizard._selected_host_ids == ["first", "second"]


async def _load_failure_keeps_order_and_reports(
    wizard: GuidedEpisodeWizard, pilot: Pilot, service: DeeperDiveService, project_id: str
) -> None:
    wizard._move_selected_host(1)
    assert wizard._selected_host_ids == ["second", "first"]
    with patch.object(
        EpisodeConfigurationService, "load_configuration", side_effect=ValueError("boom")
    ):
        wizard._load_episode_host_order()
    assert wizard._selected_host_ids == ["second", "first"]
    assert "Could not load the saved episode host order" in _status(wizard)


def test_profile_only_discard_keeps_pending_membership_order(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _profile_discard_keeps_order, with_episode=True))


def test_leave_step_discard_reverts_both_scopes(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _leave_step_discard_reverts_both, with_episode=True))


def test_no_episode_profile_discard_keeps_selection(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _no_episode_profile_discard_keeps_selection, with_episode=False))


def test_no_episode_leave_step_restores_step_entry_selection(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _no_episode_leave_step_restores_entry_selection, with_episode=False))


def test_order_load_failure_is_visible_and_keeps_current_order(tmp_path: Path) -> None:
    asyncio.run(_run(tmp_path, _load_failure_keeps_order_and_reports, with_episode=True))
