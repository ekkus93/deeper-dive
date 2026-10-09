"""Deterministic Textual acceptance for destructive action confirmation boundaries."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Button, Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp, SourcesScreen


def test_provider_removal_requires_explicit_confirmation(tmp_path: Path) -> None:
    asyncio.run(_provider_removal(tmp_path))


async def _provider_removal(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    app = DeeperDiveApp(service)
    app.provider_controller.save_provider(
        "remove-me", "fake", default_model="fake-v1", network_scope="local"
    )
    async with app.run_test(size=(110, 40)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ProvidersScreen)
        screen.query_one("#provider-name", Input).value = "remove-me"
        await pilot.pause()
        screen.action_remove()
        assert "remove-me" in app.provider_controller.config().providers
        cancel = screen.query_one("#action-cancel-provider-remove", Button)
        assert not cancel.disabled
        await pilot.pause()
        assert screen.focused is cancel

        screen.action_cancel_remove()
        assert "remove-me" in app.provider_controller.config().providers
        assert screen.query_one("#action-confirm-provider-remove", Button).disabled

        screen.action_remove()
        screen.action_confirm_remove()
        assert "remove-me" not in app.provider_controller.config().providers
        screen.action_confirm_remove()
        assert screen.query_one("#action-confirm-provider-remove", Button).disabled


def test_host_removal_requires_confirmation_and_survives_cancel(tmp_path: Path) -> None:
    asyncio.run(_host_removal(tmp_path))


async def _host_removal(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Host removal")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(110, 45)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("hosts")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HostsScreen)
        screen.query_one("#host-preset", Input).value = "custom"
        screen.query_one("#host-name", Input).value = "Fixture Host"
        screen.action_add_host()
        hosts = service.hosts(project.id).list_hosts(project.id)
        assert len(hosts) == 1
        screen.action_remove_host()
        assert len(service.hosts(project.id).list_hosts(project.id)) == 1
        cancel = screen.query_one("#host-cancel-remove", Button)
        await pilot.pause()
        assert screen.focused is cancel

        screen.action_cancel_remove_host()
        assert len(service.hosts(project.id).list_hosts(project.id)) == 1
        screen.action_remove_host()
        screen.action_confirm_remove_host()
        assert service.hosts(project.id).list_hosts(project.id) == []


def test_source_delete_is_one_shot_and_rechecks_selection(tmp_path: Path) -> None:
    asyncio.run(_source_removal(tmp_path))


async def _source_removal(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Source deletion")
    one = service.add_pasted_source(project.id, "One", "First source text.")
    two = service.add_pasted_source(project.id, "Two", "Second source text.")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(110, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("sources")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SourcesScreen)
        screen.selected_source_id = one.id
        screen.action_delete_selected()
        assert service.get_source(project.id, one.id) is not None
        await pilot.pause()
        assert screen.focused is screen.query_one("#action-cancel-source-delete", Button)

        screen.selected_source_id = two.id
        screen.action_confirm_delete()
        assert service.get_source(project.id, one.id) is not None
        assert service.get_source(project.id, two.id) is not None

        screen.selected_source_id = one.id
        screen.action_delete_selected()
        screen.action_cancel_delete()
        assert service.get_source(project.id, one.id) is not None

        screen.action_delete_selected()
        screen.action_confirm_delete()
        assert service.get_source(project.id, one.id) is None
        assert service.get_source(project.id, two.id) is not None
        screen.action_confirm_delete()
        assert service.get_source(project.id, two.id) is not None
