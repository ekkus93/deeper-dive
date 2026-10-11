"""Production-backed guided host-order add/remove/discard acceptance."""

from __future__ import annotations

import asyncio

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.hosts import HostProfile
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def test_host_order_remove_discard_save_restart(tmp_path) -> None:
    asyncio.run(_host_order_remove_discard_save_restart(tmp_path))


async def _host_order_remove_discard_save_restart(tmp_path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Host membership acceptance")
    for host_id in ("first", "second"):
        service.hosts(project.id).create_host(HostProfile(host_id, project.id, host_id).to_record())
    db = Database(service.workspaces.project_root(project.id) / "project.db")
    configs = EpisodeConfigurationService(db)
    episode = configs.create(
        project.id, EpisodeConfiguration(title="Ordered", host_ids=("first", "second"))
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
        wizard._refresh_hosts("first")
        wizard._toggle()
        wizard._remember_current_form()
        assert not wizard._current_form_dirty()

        wizard.action_remove_selected_host()
        assert wizard._selected_host_ids == ["second"]
        assert wizard._host_order_dirty()
        assert configs.load_configuration(episode.id).host_ids == ("first", "second")
        wizard._restore_discarded_form()
        assert wizard._selected_host_ids == ["first", "second"]
        assert not wizard._current_form_dirty()

        wizard.action_remove_selected_host()
        assert wizard.action_save_host_order()
        assert configs.load_configuration(episode.id).host_ids == ("second",)
        assert not wizard._host_order_dirty()
        wizard.action_select_host()
        assert wizard._selected_host_ids == ["second", "first"]
        assert wizard._host_order_dirty()
        assert wizard.action_save_host_order()
        assert not wizard._host_order_dirty()

    assert EpisodeConfigurationService(db).load_configuration(episode.id).host_ids == (
        "second",
        "first",
    )
