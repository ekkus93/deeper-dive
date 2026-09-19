from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfig, UserConfigStore


def test_preflight_tui_discloses_content_routes_and_remote_warning(tmp_path: Path) -> None:
    asyncio.run(_exercise_routing_ui(tmp_path))


async def _exercise_routing_ui(tmp_path: Path) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)),
    )
    project = service.create_project("Routing")
    service.add_pasted_source(project.id, "Notes", "Private source evidence.")
    service.hosts(project.id).create_host(
        HostProfile(
            id="host-1",
            project_id=project.id,
            display_name="Host One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(
        UserConfig(
            defaults={
                **{role.value: "fake:fake-v1" for role in ModelRole},
                "local_provider_ids": "fake-tts",
            }
        )
    )
    llm_registry = LLMProviderRegistry()
    llm_registry.register(FakeLLMProvider())
    app = DeeperDiveApp(
        service,
        provider_controller=ProviderController(
            config_store,
            llm_registry,
            {"fake-tts": FakeTTSProvider()},
        ),
        preflight_controller=PreflightController(ffmpeg_executable=ffmpeg),
    )
    async with app.run_test(size=(110, 35)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("generate")
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        routing = str(app.screen.query_one("#routing-preflight", Static).render())
        issues = str(app.screen.query_one("#preflight-issues", Static).render())
        assert "Content routing:" in routing
        assert "host_generation: fake:fake-v1 | remote | source text" in routing
        assert "tts: fake-tts | local | generated host speech text" in routing
        assert "private source text may be sent to remote provider(s): fake" in issues
