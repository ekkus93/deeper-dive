from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfig, UserConfigStore


def test_preflight_generate_starts_production_pipeline(tmp_path: Path) -> None:
    asyncio.run(_preflight_generate_starts_production_pipeline(tmp_path))


async def _preflight_generate_starts_production_pipeline(tmp_path: Path) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)),
    )
    project = service.create_project("Generate")
    service.add_pasted_source(project.id, "Notes", "Evidence for durable generation.")
    service.hosts(project.id).create_host(
        HostProfile(
            id="host-1",
            project_id=project.id,
            display_name="Host One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="Durable Episode",
            target_duration_seconds=600,
            host_ids=("host-1",),
        ),
    )
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(UserConfig(defaults={role.value: "fake:fake-v1" for role in ModelRole}))
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

    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.current_episode_id = episode.id
        app.action_navigate("generate")
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        app.screen.action_generate()
        await pilot.pause()

        assert app.current_run_id is not None
        assert isinstance(app.screen, GenerationMonitorScreen)
        for _ in range(5):
            await pilot.pause()

        run = service.runs(project.id).latest_for_episode(episode.id)
        assert run is not None
        assert run.id == app.current_run_id
        assert run.state == "completed"
        assert tuple(service.runs(project.id).list_completed_stages(run.id)) == DEFAULT_STAGES
