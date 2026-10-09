"""Durable guided-host optional-field clearing regression."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.workspace import WorkspaceManager


def test_guided_host_optional_clears_survive_fresh_service_restart(tmp_path: Path) -> None:
    asyncio.run(_guided_host_optional_clears_survive_restart(tmp_path))


async def _guided_host_optional_clears_survive_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    service = DeeperDiveService(WorkspaceManager(data_dir))
    project = service.create_project("Host clear persistence")
    repository = service.hosts(project.id)
    host = HostProfile(
        id="host-clear-fixture",
        project_id=project.id,
        display_name="Clearable Host",
        role="Original role",
        expertise="Domain knowledge",
        instructions="Original instructions",
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
        await pilot.pause()

        wizard.query_one("#guided-host-role", Input).value = ""
        wizard.query_one("#guided-host-instructions", Input).value = ""
        wizard.action_save_host()
        saved = repository.get_host(host.id)
        assert saved is not None
        assert saved.role == ""
        assert saved.instructions == ""

    restarted = DeeperDiveService(WorkspaceManager(data_dir))
    durable = restarted.hosts(project.id).get_host(host.id)
    assert durable is not None
    assert durable.role == ""
    assert durable.instructions == ""
