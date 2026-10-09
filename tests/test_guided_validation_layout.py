"""Viewport and inline-validation acceptance for the production guided wizard."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

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
        screen._apply_viewport_policy(79, 23)
        assert screen.query_one("#wizard-resize-message", Static).display
        assert not screen.query_one("#wizard-actions").display
        assert name.value == "Persistent draft"
        screen._apply_viewport_policy(*size)
        assert not screen.query_one("#wizard-resize-message", Static).display
        assert screen.query_one("#wizard-actions").display


@pytest.mark.parametrize("size", [(80, 24), (100, 30)])
def test_project_creation_runtime_failure_is_sanitized_and_retryable(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    asyncio.run(_project_creation_runtime_failure_is_sanitized_and_retryable(tmp_path, size))


async def _project_creation_runtime_failure_is_sanitized_and_retryable(
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
        name.value = "Retryable project"
        topic.value = "Synthetic question"
        with patch.object(
            service,
            "create_project",
            side_effect=RuntimeError("api_key=project-secret-canary Bearer project-bearer-canary"),
        ):
            screen.action_create_project()
        status = str(screen.query_one("#wizard-status", Static).render())
        assert "Project creation failed" in status
        assert "[REDACTED]" in status
        assert "project-secret-canary" not in status
        assert "project-bearer-canary" not in status
        assert screen.context.project_id is None
        assert name.value == "Retryable project"
        assert topic.value == "Synthetic question"
        screen.action_create_project()
        assert screen.context.project_id is not None


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
