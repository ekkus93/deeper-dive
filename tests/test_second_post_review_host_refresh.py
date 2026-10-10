"""Host membership refresh must never silently discard pending or invalid IDs."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def test_refresh_preserves_missing_and_foreign_host_ids_until_explicit_edit(
    tmp_path: Path,
) -> None:
    asyncio.run(_refresh_preserves_invalid_membership(tmp_path))


async def _refresh_preserves_invalid_membership(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Host refresh isolation")
    other_project = service.create_project("Other project")
    repository = service.hosts(project.id)
    repository.create_host(HostProfile("first-host", project.id, "First").to_record())
    repository.create_host(HostProfile("last-host", project.id, "Last").to_record())
    service.hosts(other_project.id).create_host(
        HostProfile("foreign-host", other_project.id, "Foreign").to_record()
    )
    configs = EpisodeConfigurationService(
        Database(service.workspaces.project_root(project.id) / "project.db")
    )
    episode = configs.create(
        project.id,
        EpisodeConfiguration(title="Host order", host_ids=("first-host", "last-host")),
    )
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "hosts")
        wizard._load_episode_host_order()
        wizard._refresh_hosts("first-host")
        wizard._toggle()
        wizard._remember_current_form()

        pending = ["first-host", "missing-host", "foreign-host", "last-host"]
        wizard._selected_host_ids = pending.copy()
        wizard._refresh_hosts()
        await pilot.pause()

        assert wizard._selected_host_ids == pending
        assert wizard._host_order_dirty()
        display = str(wizard.query_one("#guided-host-order", Static).render())
        assert display.count("Unavailable host") == 2
        assert "1. First" in display
        assert "4. Last" in display

        # A production save rejects the whole invalid order, preserving the
        # original durable membership rather than silently pruning the IDs.
        assert not wizard.action_save_host_order()
        assert wizard._selected_host_ids == pending
        assert configs.load_configuration(episode.id).host_ids == (
            "first-host",
            "last-host",
        )
