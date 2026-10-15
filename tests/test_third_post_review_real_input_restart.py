"""TPR-18: host order survives a real save-and-exit and a fresh app (draft store restart)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import click, reach_hosts, wait_until
from textual.pilot import Pilot

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.storage.workspace import WorkspaceManager


def _app(data: Path) -> GuidedDeeperDiveApp:
    return GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(data)))


async def _press_escape_and_save(pilot: Pilot[None], wizard: GuidedEpisodeWizard) -> None:
    await pilot.press("escape")
    await wait_until(pilot, lambda: wizard._exit_confirmation_pending)
    assert wizard._exit_confirmation_pending, "dirty order must prompt before leaving"
    await click(pilot, "#wizard-confirm-save")
    assert wizard.save_exit_requested


def test_unsaved_host_order_saved_from_escape_prompt_survives_fresh_app(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    data = tmp_path / "data"
    first = _app(data)
    async with first.run_test(size=(100, 45)) as pilot:
        await reach_hosts(pilot)
        wizard = first.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        await click(pilot, "#guided-host-recommended")
        await click(pilot, "#guided-host-order-save")
        saved_order = list(wizard._selected_host_ids)
        assert len(saved_order) == 2 and not wizard._host_order_dirty()

        # Move the selected host down with a real click: an unsaved order edit.
        await click(pilot, "#guided-host-down")
        reordered = list(wizard._selected_host_ids)
        assert reordered == [saved_order[1], saved_order[0]]
        assert wizard._host_order_dirty()
        episode_id = wizard.context.episode_id
        project_id = wizard.context.project_id

        await _press_escape_and_save(pilot, wizard)

    # A completely fresh app instance: only the workspace and draft store survive.
    second = _app(data)
    async with second.run_test(size=(100, 45)) as pilot:
        await pilot.pause()
        second.action_navigate("resume")
        await pilot.pause()
        await pilot.pause()
        resumed = second.screen
        assert isinstance(resumed, GuidedEpisodeWizard)
        assert resumed.context.project_id == project_id
        assert resumed.context.episode_id == episode_id
        assert resumed.context.state.current_step == "hosts"
        assert resumed._selected_host_ids == reordered
        assert not resumed._host_order_dirty()
