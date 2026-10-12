"""Create Host must not overwrite an edited, already-selected host profile."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("resolution", ("cancel", "discard", "save"))
def test_create_host_requires_explicit_dirty_profile_decision(
    tmp_path: Path, resolution: str
) -> None:
    asyncio.run(_create_host_requires_explicit_decision(tmp_path, resolution))


async def _create_host_requires_explicit_decision(tmp_path: Path, resolution: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Host creation guard")
    repository = service.hosts(project.id)
    repository.create_host(HostProfile("original", project.id, "Durable host").to_record())
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._refresh_hosts("original")
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        name = wizard.query_one("#guided-host-name", Input)
        assert name.value == "Durable host"
        name.value = "Unsaved original edit"
        await pilot.pause()
        assert wizard._host_profile_dirty()
        assert not wizard.action_create_host()
        await pilot.pause()
        assert wizard._pending_transition == "create-host"
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")
        assert len(repository.list_hosts(project.id)) == 1
        assert repository.get_host("original").display_name == "Durable host"
        assert name.value == "Unsaved original edit"

        if resolution == "cancel":
            wizard.action_cancel_exit_confirmation()
            await pilot.pause()
            assert name.value == "Unsaved original edit"
            assert wizard._host_profile_dirty()
            assert len(repository.list_hosts(project.id)) == 1
            assert repository.get_host("original").display_name == "Durable host"
        elif resolution == "discard":
            wizard.action_confirm_discard_exit()
            await pilot.pause()
            assert repository.get_host("original").display_name == "Durable host"
            assert len(repository.list_hosts(project.id)) == 2
        else:
            wizard.action_confirm_save_exit()
            await pilot.pause()
            assert repository.get_host("original").display_name == "Unsaved original edit"
            assert len(repository.list_hosts(project.id)) == 2
        assert not wizard.query_one("#wizard-exit-confirmation").display
        if resolution != "cancel":
            assert name.value != "Unsaved original edit"
            assert str(wizard.query_one("#wizard-status", Static).render()).startswith(
                "Created host "
            )
