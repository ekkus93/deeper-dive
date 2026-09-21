from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfig, UserConfigStore


def test_generate_click_starts_real_pipeline_and_reuses_durable_run(tmp_path: Path) -> None:
    asyncio.run(_generate_click_starts_real_pipeline_and_reuses_durable_run(tmp_path))


async def _generate_click_starts_real_pipeline_and_reuses_durable_run(tmp_path: Path) -> None:
    service = DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 20, 21, 0, tzinfo=UTC)),
    )
    project = service.create_project("Generate integration")
    service.add_pasted_source(project.id, "Notes", "Grounded evidence for generation.")
    service.hosts(project.id).create_host(
        HostProfile(
            id="host-1",
            project_id=project.id,
            display_name="Host One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    timestamp = format_timestamp(service.clock.now())
    episode_id = str(new_episode_id())
    service.hosts(project.id).create_episode(
        EpisodeRecord(
            id=episode_id,
            project_id=project.id,
            title="Episode",
            created_at=timestamp,
            modified_at=timestamp,
        ),
        ["host-1"],
    )

    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake", encoding="utf-8")
    config_store = UserConfigStore(tmp_path / "config.json")
    config_store.save(UserConfig(defaults={role.value: "fake:fake-v1" for role in ModelRole}))
    llm_registry = LLMProviderRegistry()
    llm_registry.register(FakeLLMProvider())
    provider_controller = ProviderController(
        config_store,
        llm_registry,
        {"fake-tts": FakeTTSProvider()},
    )
    app = DeeperDiveApp(
        service,
        provider_controller=provider_controller,
        preflight_controller=PreflightController(ffmpeg_executable=ffmpeg),
    )

    async with app.run_test(size=(100, 30)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.current_episode_id = episode_id
        app.action_navigate("generate")
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)

        app.screen.action_generate()
        await pilot.pause()
        assert isinstance(app.screen, GenerationMonitorScreen)
        monitor = app.screen
        assert app.current_run_id is not None
        first_run_id = app.current_run_id
        assert monitor._task is not None
        await monitor._task
        await pilot.pause()

        run = service.runs(project.id).get(first_run_id)
        assert run is not None
        assert run.state == "completed"
        assert service.runs(project.id).list_completed_stages(first_run_id) == list(DEFAULT_STAGES)

        app.action_navigate("generate")
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        app.screen.action_generate()
        await pilot.pause()
        assert app.current_run_id == first_run_id
