from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider, TTSVoice
from deeper_dive.user_config import UserConfigStore
from deeper_dive.llm import LLMProviderRegistry
from deeper_dive.tui import DeeperDiveApp


def test_hosts_screen_supports_six_hosts_editing_relationships_and_reorder(tmp_path: Path) -> None:
    asyncio.run(_exercise_hosts(tmp_path))


async def _exercise_hosts(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Panel")
    app = DeeperDiveApp(service)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("hosts")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HostsScreen)

        for index in range(6):
            screen.query_one("#host-preset", Input).value = "custom"
            screen.query_one("#host-name", Input).value = f"Host {index + 1}"
            screen.action_add_host()
        await pilot.pause()
        assert len(service.hosts(project.id).list_hosts(project.id)) == 6

        screen.query_one("#host-role", Input).value = "moderator"
        screen.query_one("#host-expertise", Input).value = "systems"
        screen.query_one("#host-instructions", Input).value = "Ask concise questions."
        screen.query_one("#host-evidence", Input).value = "primary sources, methods"
        screen.query_one("#host-behavior", Input).value = '{"curiosity": 0.8, "turn_length": 0.4}'
        screen.query_one("#host-tts-provider", Input).value = "kitten"
        screen.query_one("#host-tts-voice", Input).value = "voice-a"
        screen.action_save_host()
        selected = service.hosts(project.id).get_host(screen.selected_host_id or "")
        assert selected is not None
        assert selected.role == "moderator"
        assert selected.tts_provider == "kitten"

        before = list(screen.display_order)
        screen._move(-1)
        assert set(screen.display_order) == set(before)
        screen.action_duplicate_host()
        assert len(service.hosts(project.id).list_hosts(project.id)) == 7
        screen.action_remove_host()
        assert len(service.hosts(project.id).list_hosts(project.id)) == 6

        screen.selected_host_id = screen.display_order[0]
        screen.query_one("#relationship-target", Input).value = screen.display_order[1]
        screen.query_one("#relationship-stance", Input).value = "skeptical peer"
        screen.action_save_relationship()
        assert len(service.hosts(project.id).list_relationships(project.id)) == 1


def test_hosts_screen_discovers_and_configures_three_kitten_voices(tmp_path: Path) -> None:
    asyncio.run(_exercise_three_kitten_voices(tmp_path))


async def _exercise_three_kitten_voices(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path))
    project = service.create_project("Three voices")
    kitten = FakeTTSProvider(provider_id="kitten", voices=tuple(TTSVoice(v, v) for v in ("Bella", "Luna", "Leo")))
    controller = ProviderController(UserConfigStore(tmp_path / "config.json"), LLMProviderRegistry(), {"kitten": kitten})
    app = DeeperDiveApp(service, provider_controller=controller)
    async with app.run_test(size=(100, 45)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("hosts")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, HostsScreen)
        for index, voice in enumerate(("Bella", "Luna", "Leo"), 1):
            screen.query_one("#host-preset", Input).value = "custom"
            screen.query_one("#host-name", Input).value = f"Host {index}"
            screen.action_add_host()
            screen.query_one("#host-tts-provider", Input).value = "kitten"
            screen.query_one("#host-tts-voice", Input).value = voice
            screen.action_save_host()
        hosts = service.hosts(project.id).list_hosts(project.id)
        assert [host.tts_voice for host in hosts] == ["Bella", "Luna", "Leo"]
        screen.action_discover_tts()
        screen.action_preview_voice()
        assert kitten.requests
