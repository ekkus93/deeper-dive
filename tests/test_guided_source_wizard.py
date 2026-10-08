"""Guided source import acceptance."""

import asyncio
from pathlib import Path

from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_guided_source_import(tmp_path: Path) -> None:
    asyncio.run(_check(tmp_path))


async def _check(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedSourceWizard)
        screen.query_one("#guided-project-name", Input).value = "Oceans"
        screen.query_one("#guided-project-topic", Input).value = "Heat?"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()
        screen.query_one("#guided-source-title", Input).value = "Notes"
        screen.query_one("#guided-source-text", Input).value = "Oceans store heat."
        for button in screen.query(Button):
            if button.name == "add-source":
                button.press()
                break
        await pilot.pause()
        sources = service.list_sources(project_id)
        assert len(sources) == 1
        assert service.list_source_chunks(project_id, sources[0].id)

def test_guided_research_choices_persist_through_production_controller(tmp_path: Path) -> None:
    asyncio.run(_guided_research_choices_persist(tmp_path))


async def _guided_research_choices_persist(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "research-data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(80, 24)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedSourceWizard)
        screen.query_one("#guided-project-name", Input).value = "Oceans"
        screen.query_one("#guided-project-topic", Input).value = "How do oceans store heat?"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()
        screen.query_one("#guided-source-title", Input).value = "Notes"
        screen.query_one("#guided-source-text", Input).value = "Oceans store heat."
        for button in screen.query(Button):
            if button.name == "add-source":
                button.press()
                break
        await pilot.pause()
        screen.action_continue()
        assert screen.context.state.current_step == "research"
        assert screen.query_one("#guided-research-policy", Select).display
        assert not screen.query_one("#guided-source-text", Input).display
        for mode in ("off", "useful", "aggressive"):
            screen.query_one("#guided-research-policy", Select).value = mode
            await pilot.pause()
            screen.action_save_research()
            assert app.composition.research_controller.policy(project_id).mode.value == mode
            assert not screen.query_one("#wizard-continue", Button).disabled
        screen.action_continue()
        assert screen.context.state.current_step == "hosts"
    restarted = GuidedDeeperDiveApp(service)
    assert restarted.composition.research_controller.policy(project_id).mode.value == "aggressive"
