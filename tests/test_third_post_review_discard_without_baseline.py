"""TPR-09: Discard with no recorded baseline fails closed instead of adopting input."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_discard_without_baseline_clears_unsaved_input(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        wizard.query_one("#guided-project-name", Input).value = "Project"
        wizard.query_one("#guided-project-topic", Input).value = "Topic"
        assert wizard.action_create_project()
        await pilot.pause()
        assert wizard.action_continue()
        await pilot.pause()
        assert wizard.context.state.current_step == "sources"

        body = wizard.query_one("#guided-source-text", Input)
        body.value = "PASTED-BODY-CANARY"
        # Simulate a step whose baseline was never recorded.
        wizard._form_baselines.pop("sources", None)
        wizard._form_baseline_targets.pop("sources", None)
        assert wizard._current_form_dirty()

        wizard.action_back()
        await pilot.pause()
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_discard_exit()
        await pilot.pause()

        # Back left the sources step; return and verify nothing was retained.
        wizard.context.state = wizard.context.state.__class__(wizard.context.state.kind, "sources")
        wizard._toggle()
        assert body.value == ""
        assert "PASTED-BODY-CANARY" not in str(wizard.query_one("#wizard-status", Static).render())
