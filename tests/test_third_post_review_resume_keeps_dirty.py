"""TPR-17: re-entering a New Deep Dive wizard never adopts unsaved edits as the clean baseline."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import add_pasted_source, click, continue_step, create_project, type_into
from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_screen_resume_with_unsaved_edits_keeps_them_dirty(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 40)) as pilot:
        app._first_run_readiness.close()
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        await create_project(pilot, "Resume dirty", "Topic")
        await continue_step(pilot, "sources")
        await add_pasted_source(pilot, "Notes", "Evidence text for the resume test.")
        await continue_step(pilot, "research")
        await click(pilot, "#guided-research-save")
        await continue_step(pilot, "hosts")
        await click(pilot, "#guided-host-recommended")
        await click(pilot, "#guided-host-order-save")
        await continue_step(pilot, "episode")

        await type_into(pilot, "#guided-episode-title", "Unsaved title")
        assert wizard._current_form_dirty()

        wizard.on_screen_resume()
        await pilot.pause()

        assert wizard._current_form_dirty()
        assert wizard.query_one("#guided-episode-title", Input).value == "Unsaved title"
