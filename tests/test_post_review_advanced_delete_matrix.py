"""Textual acceptance for provider, host and source destructive confirmations."""

from __future__ import annotations

import asyncio
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.hosts import HostProfile
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp, SourcesScreen
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_provider_deletion_requires_confirmation_and_selection_stability(tmp_path: Path) -> None:
    asyncio.run(_provider_deletion(tmp_path))


async def _provider_deletion(tmp_path: Path) -> None:
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(
        UserConfig(
            providers={
                "one": ProviderConfig(provider_type="fake"),
                "two": ProviderConfig(provider_type="fake"),
            }
        )
    )
    controller = ProviderController(config_store, LLMProviderRegistry(), {})
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    app = DeeperDiveApp(service, provider_controller=controller)
    async with app.run_test(size=(100, 40)) as pilot:
        app.action_navigate("providers")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, ProvidersScreen)

        screen.action_remove()
        assert len(controller.config().providers) == 2
        screen.action_cancel_remove()
        screen.action_confirm_remove()
        assert len(controller.config().providers) == 2

        screen.action_remove()
        screen.selected_provider = "two"
        screen.action_confirm_remove()
        assert len(controller.config().providers) == 2

        screen.selected_provider = "one"
        screen.action_remove()
        screen.action_confirm_remove()
        assert "one" not in controller.config().providers
        screen.action_confirm_remove()
        assert "two" in controller.config().providers


def test_host_deletion_requires_confirmation_and_selection_stability(tmp_path: Path) -> None:
    asyncio.run(_host_deletion(tmp_path))


async def _host_deletion(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Host deletion")
    repository = service.hosts(project.id)
    first = HostProfile("host-one", project.id, "First Host")
    second = HostProfile("host-two", project.id, "Second Host")
    repository.create_host(first.to_record())
    repository.create_host(second.to_record())
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("hosts")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HostsScreen)
        screen.selected_host_id = first.id
        screen.action_remove_host()
        assert repository.get_host(first.id) is not None
        screen.action_cancel_remove_host()
        screen.action_confirm_remove_host()
        assert repository.get_host(first.id) is not None

        screen.action_remove_host()
        screen.selected_host_id = second.id
        screen.action_confirm_remove_host()
        assert repository.get_host(first.id) is not None
        assert repository.get_host(second.id) is not None

        screen.selected_host_id = first.id
        screen.action_remove_host()
        screen.action_confirm_remove_host()
        assert repository.get_host(first.id) is None
        screen.action_confirm_remove_host()
        assert repository.get_host(second.id) is not None


def test_source_deletion_requires_confirmation_and_selection_stability(tmp_path: Path) -> None:
    asyncio.run(_source_deletion(tmp_path))


async def _source_deletion(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Source deletion")
    source_a = service.add_pasted_source(project.id, "Source A", "Alpha facts")
    source_b = service.add_pasted_source(project.id, "Source B", "Beta facts")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("sources")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, SourcesScreen)
        screen.selected_source_id = source_a.id
        screen.action_delete_selected()
        assert service.get_source(project.id, source_a.id) is not None
        screen.action_cancel_delete()
        screen.action_confirm_delete()
        assert service.get_source(project.id, source_a.id) is not None

        screen.action_delete_selected()
        screen.selected_source_id = source_b.id
        screen.action_confirm_delete()
        assert service.get_source(project.id, source_a.id) is not None
        assert service.get_source(project.id, source_b.id) is not None

        screen.selected_source_id = source_a.id
        screen.action_delete_selected()
        screen.action_confirm_delete()
        assert service.get_source(project.id, source_a.id) is None
        screen.action_confirm_delete()
        assert service.get_source(project.id, source_b.id) is not None
