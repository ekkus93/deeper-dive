"""Viewport and inline-validation acceptance for the production guided wizard."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_shell import NewDeepDiveWizardShell


@pytest.mark.parametrize("size", [(80, 24), (100, 30)])
def test_project_validation_is_inline_and_preserves_draft(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    asyncio.run(_project_validation_is_inline_and_preserves_draft(tmp_path, size))


async def _project_validation_is_inline_and_preserves_draft(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=size) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        name = screen.query_one("#guided-project-name", Input)
        topic = screen.query_one("#guided-project-topic", Input)
        screen.action_create_project()
        await pilot.pause()
        assert "Error: Project name is required." in str(
            screen.query_one("#guided-project-name-error", Static).render()
        )
        assert "Error: Main curiosity is required." in str(
            screen.query_one("#guided-project-topic-error", Static).render()
        )
        assert screen.focused is name
        assert screen.context.project_id is None

        name.value = "Persistent draft"
        screen.action_create_project()
        await pilot.pause()
        assert screen.focused is topic
        assert name.value == "Persistent draft"
        assert "needs attention" in str(screen.query_one("#wizard-status", Static).render())

        topic.value = "How does it work?"
        screen.action_create_project()
        assert screen.context.project_id is not None
        assert name.value == "Persistent draft"
        assert topic.value == "How does it work?"
        for field in ("name", "topic", "audience"):
            assert not str(screen.query_one(f"#guided-project-{field}-error", Static).render())


@pytest.mark.parametrize("width", [80, 100])
def test_progress_rail_fits_terminal_width(tmp_path: Path, width: int) -> None:
    composition = ProductionComposition.build(
        service=DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    )
    context = WizardContext(composition, WizardState(WizardKind.NEW_DEEP_DIVE, "sources"))
    screen = NewDeepDiveWizardShell(context, lambda key: key == "project")
    screen._viewport_width = width
    progress = screen._progress_text(screen.navigator)
    assert "✓ Project Setup (complete)" in progress
    assert "▶ Sources (current)" in progress
    assert len(progress) <= width - 4
    assert "\n" not in progress
