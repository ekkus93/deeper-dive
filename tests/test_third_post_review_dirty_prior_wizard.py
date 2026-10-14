"""TPR-02: a dirty prior New Deep Dive wizard is never silently reset."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager


def test_dirty_prior_wizard_prompts_before_new_deep_dive_resets_it(tmp_path: Path) -> None:
    asyncio.run(_exercise(tmp_path))


async def _exercise(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        wizard.query_one("#guided-project-name", Input).value = "Oceans"
        wizard.query_one("#guided-project-topic", Input).value = "Tides"
        assert wizard.action_create_project()
        project_id = wizard.context.project_id
        assert project_id is not None
        wizard.query_one("#guided-project-topic", Input).value = "Unsaved new topic"
        assert wizard._current_form_dirty()

        # Something other than the wizard's own guarded navigation buries it.
        app.push_screen("home")
        await pilot.pause()
        assert app.screen is not wizard

        app.action_navigate("new")
        await pilot.pause()
        await pilot.pause()

        # The old wizard is back on top with its prompt; nothing was reset.
        assert app.screen is wizard
        assert wizard._exit_confirmation_pending
        assert wizard.context.project_id == project_id
        assert wizard.query_one("#guided-project-topic", Input).value == "Unsaved new topic"
        status = str(wizard.query_one("#wizard-status", Static).render())
        assert "Oceans" in status

        # Discard then proceeds to a genuinely fresh wizard.
        wizard.action_confirm_discard_exit()
        await pilot.pause()
        await pilot.pause()
        fresh = app.screen
        assert fresh is not wizard
        assert fresh.context.project_id is None
        assert fresh.query_one("#guided-project-topic", Input).value == ""
