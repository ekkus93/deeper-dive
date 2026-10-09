"""Textual pilots for shared dirty-form Save and Exit behavior."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button, Input, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.storage.workspace import WorkspaceManager


def test_first_run_dirty_form_saves_through_real_provider_service(tmp_path: Path) -> None:
    asyncio.run(_first_run_valid(tmp_path))


async def _first_run_valid(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)
        screen.action_continue()
        screen.action_continue()
        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()
        await pilot.pause()

        screen.query_one("#setup-provider-name", Input).value = "fixture"
        screen.query_one("#setup-provider-adapter", Input).value = "fake"
        screen.query_one("#setup-provider-model", Input).value = "fake-v1"
        screen.query_one("#setup-provider-network", Input).value = "local"
        await pilot.pause()
        screen.action_save_exit()
        assert app.screen is screen
        assert screen.query_one("#wizard-exit-confirmation").display
        await pilot.pause()
        assert screen.focused is screen.query_one("#wizard-confirm-cancel", Button)
        assert "fixture" not in app.provider_controller.config().providers
        screen.action_confirm_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"
        assert app.provider_controller.config().providers["fixture"].default_model == "fake-v1"


def test_invalid_dirty_first_run_keeps_input_and_discard_does_not_persist_secret(
    tmp_path: Path,
) -> None:
    asyncio.run(_first_run_invalid(tmp_path))


async def _first_run_invalid(tmp_path: Path) -> None:
    app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
    async with app.run_test(size=(100, 35)) as pilot:
        screen = app.screen
        assert isinstance(screen, GuidedFirstRunWizard)
        screen.action_continue()
        screen.action_continue()
        screen.query_one("#setup-ai-choice", Select).value = "manual"
        await pilot.pause()
        screen.action_continue()
        await pilot.pause()

        screen.query_one("#setup-provider-name", Input).value = "unsafe"
        screen.query_one("#setup-provider-adapter", Input).value = "openai"
        screen.query_one("#setup-provider-model", Input).value = "fixture-model"
        screen.query_one("#setup-provider-credential-env", Input).value = "sk-raw-input-canary"
        await pilot.pause()
        screen.action_save_exit()
        screen.action_confirm_save_exit()
        assert app.screen is screen
        assert screen.query_one("#setup-provider-credential-env", Input).value == (
            "sk-raw-input-canary"
        )
        assert "unsafe" not in app.provider_controller.config().providers
        screen.action_save_exit()
        await pilot.press("escape")
        assert app.screen is screen
        assert not screen.query_one("#wizard-exit-confirmation").display
        screen.action_save_exit()
        screen.action_confirm_discard_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"
        draft = tmp_path / "data" / "guided-first-run-draft.json"
        assert draft.exists()
        assert "sk-raw-input-canary" not in draft.read_text(encoding="utf-8")


def test_new_project_dirty_save_exit_writes_project_and_navigates_home(tmp_path: Path) -> None:
    asyncio.run(_new_project_valid(tmp_path))


async def _new_project_valid(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#guided-project-name", Input).value = "Dirty project"
        screen.query_one("#guided-project-topic", Input).value = "What persists?"
        await pilot.pause()
        screen.action_save_exit()
        assert screen.query_one("#wizard-exit-confirmation").display
        screen.action_confirm_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"
        projects = service.list_project_summaries()
        assert any(project.name == "Dirty project" for project in projects)


def test_explicit_new_project_save_resets_dirty_baseline(tmp_path: Path) -> None:
    asyncio.run(_explicit_new_project_save_resets_dirty_baseline(tmp_path))


async def _explicit_new_project_save_resets_dirty_baseline(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#guided-project-name", Input).value = "Clean saved project"
        screen.query_one("#guided-project-topic", Input).value = "Persist before exit"
        await pilot.pause()
        assert screen._current_form_dirty()
        screen.action_create_project()
        assert not screen._current_form_dirty()
        screen.action_save_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"
        assert any(
            project.name == "Clean saved project" for project in service.list_project_summaries()
        )


def test_new_deep_dive_pasted_source_discard_retains_only_durable_project(
    tmp_path: Path,
) -> None:
    asyncio.run(_new_source_discard(tmp_path))


async def _new_source_discard(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#guided-project-name", Input).value = "Saved project"
        screen.query_one("#guided-project-topic", Input).value = "Retain only durable records"
        screen.action_create_project()
        project_id = screen.context.project_id
        assert project_id is not None
        screen.action_continue()
        await pilot.pause()
        assert screen.context.state.current_step == "sources"
        screen.query_one("#guided-source-title", Input).value = "Unsaved title canary"
        screen.query_one("#guided-source-text", Input).value = "Unsaved source body canary"
        await pilot.pause()
        screen.action_save_exit()
        assert app.screen is screen
        assert screen.query_one("#wizard-exit-confirmation").display
        screen.action_cancel_exit_confirmation()
        assert "Unsaved source body canary" in screen.query_one("#guided-source-text", Input).value
        screen.action_save_exit()
        screen.action_confirm_discard_exit()
        await pilot.pause()
        assert app.screen.id == "screen-home"
        assert service.open_project(project_id) is not None
        assert not service.list_sources(project_id)
        draft = tmp_path / "data" / "guided-new-deep-dive-draft.json"
        assert draft.exists()
        assert "Unsaved source body canary" not in draft.read_text(encoding="utf-8")


def test_partial_pasted_source_is_not_discarded_by_other_source_import(tmp_path: Path) -> None:
    asyncio.run(_partial_source_preserved(tmp_path))


async def _partial_source_preserved(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = GuidedDeeperDiveApp(service)
    source_file = tmp_path / "source.md"
    source_file.write_text("Durable source content for research.", encoding="utf-8")
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        screen = app.screen
        screen.query_one("#guided-project-name", Input).value = "Partial source project"
        screen.query_one("#guided-project-topic", Input).value = "Unfinished source"
        screen.action_create_project()
        screen.action_continue()
        await pilot.pause()
        assert screen.context.state.current_step == "sources"
        screen.query_one("#guided-source-title", Input).value = "Incomplete paste"
        screen.query_one("#guided-source-paths", Input).value = str(source_file)
        await pilot.pause()
        screen.action_save_exit()
        assert screen.query_one("#wizard-exit-confirmation").display
        screen.action_confirm_save_exit()
        assert app.screen is screen
        assert screen.query_one("#guided-source-title", Input).value == "Incomplete paste"
        assert screen.query_one("#guided-source-paths", Input).value == str(source_file)
        assert not service.list_sources(screen.context.project_id)


def test_delayed_baseline_cannot_swallow_form_edits() -> None:
    from types import SimpleNamespace
    from typing import cast

    from deeper_dive.wizard_shell import WizardShell

    callbacks = []
    entered = ["initial"]
    fake = SimpleNamespace(
        context=SimpleNamespace(state=SimpleNamespace(current_step="sources")),
        _form_baselines={},
        _editable_snapshot=lambda: (("guided-source-text", entered[0]),),
        call_after_refresh=lambda callback: callbacks.append(callback),
    )
    WizardShell._schedule_form_baseline(cast(WizardShell, fake))
    entered[0] = "new unsaved user input"
    callbacks.pop()()
    assert "sources" not in fake._form_baselines

    WizardShell._schedule_form_baseline(cast(WizardShell, fake))
    callbacks.pop()()
    assert fake._form_baselines["sources"] == (("guided-source-text", "new unsaved user input"),)
