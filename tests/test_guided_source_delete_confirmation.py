"""Guided source deletion requires fresh confirmation after navigation or selection."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, Select, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.storage.workspace import WorkspaceManager


@pytest.mark.parametrize("size", [(80, 24), (100, 30)])
def test_guided_source_delete_confirmation_resets_on_navigation_and_selection(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    asyncio.run(_verify_delete_confirmation(tmp_path, size))


async def _verify_delete_confirmation(tmp_path: Path, size: tuple[int, int]) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=size) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedEpisodeWizard)
        screen.query_one("#guided-project-name", Input).value = "Deletion safety"
        screen.query_one("#guided-project-topic", Input).value = "Synthetic source evidence"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()
        assert screen.context.state.current_step == "sources"

        for title in ("First evidence", "Second evidence"):
            screen.query_one("#guided-source-title", Input).value = title
            screen.query_one("#guided-source-text", Input).value = f"Contents of {title}"
            screen.action_add_pasted_source()
            await pilot.pause()

        sources = service.list_sources(project_id)
        assert len(sources) == 2
        first, second = sources
        picker = screen.query_one("#guided-source-picker", Select)
        picker.value = first.id
        await pilot.pause()

        screen.action_delete_source()
        assert screen._pending_delete_source_id == first.id
        assert "again to confirm" in str(
            screen.query_one("#wizard-status", Static).render()
        )
        assert len(service.list_sources(project_id)) == 2

        # Back and Continue are not a second confirmation.
        screen.action_back()
        assert screen.context.state.current_step == "project"
        assert screen._pending_delete_source_id is None
        screen.action_continue()
        assert screen.context.state.current_step == "sources"
        screen.action_delete_source()
        assert len(service.list_sources(project_id)) == 2

        # Switching rows must disarm the prior source's pending deletion.
        picker.value = second.id
        await pilot.pause()
        assert screen._pending_delete_source_id is None
        screen.action_delete_source()
        assert screen._pending_delete_source_id == second.id
        picker.value = first.id
        await pilot.pause()
        assert screen._pending_delete_source_id is None
        screen.action_delete_source()
        assert len(service.list_sources(project_id)) == 2
        screen.action_delete_source()
        remaining = service.list_sources(project_id)
        assert [source.id for source in remaining] == [second.id]
        assert screen._pending_delete_source_id is None
