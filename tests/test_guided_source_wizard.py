"""Guided source import acceptance."""

import asyncio
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.parsing import ParsedBlock, ParseResult
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


def test_guided_project_and_multi_source_actions_use_production_services(tmp_path: Path) -> None:
    asyncio.run(_guided_project_and_multi_source_actions(tmp_path))


async def _guided_project_and_multi_source_actions(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "source-actions"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedSourceWizard)

        screen.query_one("#guided-project-name", Input).value = "Energy"
        screen.query_one("#guided-project-topic", Input).value = "How does storage scale?"
        screen.query_one("#guided-project-audience", Select).value = "technical"
        screen.query_one(
            "#guided-project-description", Input
        ).value = "Compare practical tradeoffs."
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        project = service.open_project(project_id)
        assert project is not None
        assert "Main curiosity: How does storage scale?" in project.instructions
        assert "Audience: technical" in project.instructions
        assert "Description: Compare practical tradeoffs." in project.instructions

        screen.action_continue()
        assert screen.context.state.current_step == "sources"

        single = tmp_path / "single.txt"
        single.write_text("Single-file evidence.", encoding="utf-8")
        folder = tmp_path / "folder"
        folder.mkdir()
        (folder / "nested.txt").write_text("Folder evidence.", encoding="utf-8")
        screen.query_one("#guided-source-paths", Input).value = f"{single},{folder}"
        screen.action_add_file_sources()
        await pilot.pause()

        with patch(
            "deeper_dive.application.service.HtmlUrlParser.fetch_user_url",
            return_value=ParseResult(
                "html-url",
                "1",
                (ParsedBlock(0, "Fetched URL evidence.", location="paragraph:1"),),
                metadata={"content_hash": "url-fixture-hash"},
            ),
        ):
            screen.query_one("#guided-source-urls", Input).value = "https://example.test/evidence"
            screen.action_add_url_sources()
        await pilot.pause()

        sources = service.list_sources(project_id)
        assert len(sources) == 3
        assert all(service.list_source_chunks(project_id, source.id) for source in sources)
        summary = str(screen.query_one("#guided-source-summary").render())
        assert "included" in summary
        assert "parsed" in summary

        picker = screen.query_one("#guided-source-picker", Select)
        selected_id = sources[0].id
        picker.value = selected_id
        await pilot.pause()
        screen.action_toggle_source()
        assert service.get_source(project_id, selected_id).included is False

        screen.action_toggle_source()
        assert service.get_source(project_id, selected_id).included is True
        screen.action_delete_source()
        assert service.get_source(project_id, selected_id) is not None
        screen.action_delete_source()
        assert service.get_source(project_id, selected_id) is None

        screen.action_continue()
        assert screen.context.state.current_step == "research"


def test_guided_source_import_failure_retains_form_then_resumes_after_restart(
    tmp_path: Path,
) -> None:
    asyncio.run(_source_import_failure_retry_and_restart(tmp_path))


async def _source_import_failure_retry_and_restart(tmp_path: Path) -> None:
    workspace = WorkspaceManager(tmp_path / "restart-source")
    service = DeeperDiveService(workspace)
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 30)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, GuidedSourceWizard)
        screen.query_one("#guided-project-name", Input).value = "Resumable sources"
        screen.query_one("#guided-project-topic", Input).value = "What is reproducible?"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()
        screen.query_one("#guided-source-title", Input).value = "Preserved title"
        screen.query_one("#guided-source-text", Input).value = "Indexable source content"
        with patch.object(
            service, "add_pasted_source", side_effect=ValueError("synthetic parse error")
        ):
            screen.action_add_pasted_source()
        assert screen.query_one("#guided-source-title", Input).value == "Preserved title"
        assert screen.query_one("#guided-source-text", Input).value == "Indexable source content"
        assert not service.list_sources(project_id)
        screen.action_add_pasted_source()
        assert len(service.list_sources(project_id)) == 1
        screen.action_continue()
        assert screen.context.state.current_step == "research"
        screen.action_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"

    restarted = GuidedDeeperDiveApp(DeeperDiveService(workspace))
    async with restarted.run_test(size=(100, 30)) as pilot:
        await pilot.pause()
        assert restarted.screen.id == "screen-home"
        button = restarted.screen.query_one("#action-resume-deep-dive", Button)
        assert button.display
        button.press()
        await pilot.pause()
        assert isinstance(restarted.screen, GuidedSourceWizard)
        assert restarted.screen.context.project_id == project_id
        assert restarted.screen.context.state.current_step == "research"
