"""Textual global-navigation matrix for New Deep Dive editable controls."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize(
    ("step", "selector"),
    [
        ("project", "guided-project-name"),
        ("project", "guided-project-topic"),
        ("project", "guided-project-audience"),
        ("project", "guided-project-description"),
        ("sources", "guided-source-title"),
        ("sources", "guided-source-text"),
        ("sources", "guided-source-paths"),
        ("sources", "guided-source-urls"),
        ("research", "guided-research-policy"),
        ("hosts", "guided-host-name"),
        ("hosts", "guided-host-role"),
        ("hosts", "guided-host-expertise"),
        ("hosts", "guided-host-instructions"),
        ("episode", "guided-episode-title"),
        ("episode", "guided-episode-focus"),
        ("episode", "guided-episode-duration"),
        ("episode", "guided-episode-custom-duration"),
        ("episode", "guided-episode-audience"),
        ("episode", "guided-episode-depth"),
        ("episode", "guided-episode-must-cover"),
        ("episode", "guided-episode-avoid"),
    ],
)
def test_global_navigation_cancel_and_discard_for_new_wizard_field(
    tmp_path: Path, step: str, selector: str
) -> None:
    asyncio.run(_check_navigation(tmp_path, step, selector))


async def _check_navigation(tmp_path: Path, step: str, selector: str) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Global navigation matrix")
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, step)
        if selector == "guided-episode-custom-duration":
            wizard.query_one("#guided-episode-duration", Select).value = "custom"
        if selector == "guided-episode-depth":
            wizard._episode_advanced = True
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        field = wizard.query_one(f"#{selector}")
        original = field.value
        if isinstance(field, Input):
            field.value = str(original) + " pending edit"
        else:
            assert isinstance(field, Select)
            alternatives = {
                "guided-project-audience": ("technical", "expert"),
                "guided-research-policy": ("off", "aggressive"),
                "guided-episode-duration": ("30", "10"),
                "guided-episode-audience": ("technical", "expert"),
                "guided-episode-depth": ("deep", "accessible"),
            }
            choices = alternatives[selector]
            field.value = choices[0] if original != choices[0] else choices[1]
        pending = field.value
        assert pending != original
        assert wizard._current_form_dirty()

        app.action_navigate("home")
        assert app.screen is wizard
        assert wizard.query_one("#wizard-exit-confirmation").display
        assert field.value == pending
        await pilot.pause()
        assert wizard.focused is wizard.query_one("#wizard-confirm-cancel")

        wizard.action_cancel_exit_confirmation()
        assert not wizard.query_one("#wizard-exit-confirmation").display
        assert field.value == pending
        assert wizard._current_form_dirty()

        app.action_navigate("home")
        assert wizard.query_one("#wizard-exit-confirmation").display
        wizard.action_confirm_discard_exit()
        assert field.value == original
        await pilot.pause()
        assert app.screen.id == "screen-home"
