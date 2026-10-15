"""TPR-18: one real click runs a wizard handler exactly once (no per-class re-dispatch)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import BUTTON_SETTLE_SECONDS
from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_one_click_on_continue_advances_first_run_by_exactly_one_step(tmp_path: Path) -> None:
    asyncio.run(_first_run(tmp_path))


async def _first_run(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        wizard = app.screen
        assert wizard.context.state.current_step == "welcome"
        await pilot.click("#wizard-continue")
        await pilot.pause(BUTTON_SETTLE_SECONDS)
        assert wizard.context.state.current_step == "system-check"
        await pilot.click("#wizard-back")
        await pilot.pause(BUTTON_SETTLE_SECONDS)
        assert wizard.context.state.current_step == "welcome"


def test_one_click_on_continue_advances_new_deep_dive_by_exactly_one_step(
    tmp_path: Path,
) -> None:
    asyncio.run(_new_deep_dive(tmp_path))


async def _new_deep_dive(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        app._first_run_readiness.close()
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        wizard.query_one("#guided-project-name", Input).value = "One click"
        wizard.query_one("#guided-project-topic", Input).value = "Topic"
        assert wizard.action_create_project()
        steps_before = wizard.context.state.current_step
        await pilot.click("#wizard-continue")
        await pilot.pause(BUTTON_SETTLE_SECONDS)
        keys = [step.key for step in wizard.navigator.steps]
        assert keys.index(wizard.context.state.current_step) == keys.index(steps_before) + 1
