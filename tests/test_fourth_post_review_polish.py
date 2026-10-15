"""FPR-19: field labels in statuses, project button text, Create Host scope."""

from __future__ import annotations

import asyncio
from pathlib import Path

from guided_pilot import click, create_project, reach_hosts
from textual.widgets import Button, Select

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.wizard_transitions import _FORM_FIELDS, field_label


def test_every_form_field_has_a_human_label() -> None:
    for _kind, step in _FORM_FIELDS:
        for key in _FORM_FIELDS[(_kind, step)]:
            label = field_label(key)
            assert label and "-" not in label and label != key, (key, label)
            assert not label.lower().startswith(("setup", "guided")), (key, label)
    assert field_label("setup-host1-voice") == "Host 1 voice"
    assert field_label("guided-episode-audience") == "Episode audience"


def test_unavailable_selection_status_uses_labels_not_widget_ids(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await pilot.pause()
            wizard = app.screen
            wizard._discard_unavailable = ("setup-host1-voice",)
            wizard.set_status(wizard._unavailable_status(("setup-host1-voice",)))
            status = str(wizard.query_one("#wizard-status").render())
            assert "Host 1 voice" in status and "setup-host1-voice" not in status

    asyncio.run(run())


def test_project_button_says_save_once_the_project_exists(tmp_path: Path) -> None:
    async def run() -> None:
        app = GuidedDeeperDiveApp(DeeperDiveService(WorkspaceManager(tmp_path / "data")))
        async with app.run_test(size=(100, 45)) as pilot:
            await pilot.pause()
            app._first_run_readiness.close()
            app.action_navigate("new")
            await pilot.pause()
            button = app.screen.query_one("#guided-project-create", Button)
            assert str(button.label) == "Create Project"
            await create_project(pilot, "Real", "Topic")
            assert str(button.label) == "Save Project"

    asyncio.run(run())


def test_create_host_is_allowed_again_after_selecting_a_different_host(tmp_path: Path) -> None:
    async def run() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        app = GuidedDeeperDiveApp(service)
        async with app.run_test(size=(100, 45)) as pilot:
            await reach_hosts(pilot)
            wizard = app.screen
            project_id = wizard.context.project_id
            await click(pilot, "#guided-host-recommended")
            picker = wizard.query_one("#guided-host-picker", Select)
            original = picker.value
            before = len(service.hosts(project_id).list_hosts(project_id))

            # Create clones the unchanged form into a new host, which becomes the target.
            await click(pilot, "#guided-host-create")
            assert len(service.hosts(project_id).list_hosts(project_id)) == before + 1
            clone = picker.value
            assert clone != original
            # An immediate identical repeat is still a double-submit and is refused.
            await click(pilot, "#guided-host-create")
            assert len(service.hosts(project_id).list_hosts(project_id)) == before + 1

            # Back on the original host the form shows identical values, but this is a
            # different target: the double-submit window is over and Create works again.
            picker.value = original
            await pilot.pause()
            assert wizard._loaded_host_id == original
            await click(pilot, "#guided-host-create")
            assert len(service.hosts(project_id).list_hosts(project_id)) == before + 2

    asyncio.run(run())
