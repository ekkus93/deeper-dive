from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock, format_timestamp
from deeper_dive.domain.ids import new_episode_id
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.preflight_screen import PreflightController
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.episode_repositories import EpisodeRecord
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_generate_starts_real_pipeline_and_reuses_active_run(tmp_path: Path) -> None:
    asyncio.run(_generate_starts_real_pipeline_and_reuses_active_run(tmp_path))


async def _generate_starts_real_pipeline_and_reuses_active_run(tmp_path: Path) -> None:
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
    config_store = UserConfigStore(service.workspaces.data_dir / "config.json")
    config_store.save(
        UserConfig(
            providers={
                "fake": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "fake-tts": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: "fake:fake-v1" for role in ModelRole},
        )
    )
    llm_registry = LLMProviderRegistry()
    llm_registry.register(FakeLLMProvider())
    provider_controller = ProviderController(
        config_store,
        llm_registry,
        {"fake-tts": FakeTTSProvider()},
    )
    preflight_controller = PreflightController(ffmpeg_executable=ffmpeg)
    app = DeeperDiveApp(
        service,
        provider_controller=provider_controller,
        preflight_controller=preflight_controller,
    )
    app.current_project_id = project.id
    app.current_project_name = project.name
    app.current_episode_id = episode_id

    first = preflight_controller.start_generation(app)
    repeated = preflight_controller.start_generation(app)
    assert repeated.id == first.id

    presentation = preflight_controller.build(app)
    assert presentation.report.ready
    assert app.generation_monitor_controller.runner is not None
    await asyncio.wait_for(app.generation_monitor_controller.run(first.id), timeout=5.0)

    run = service.runs(project.id).get(first.id)
    assert run is not None
    assert run.state == "completed"
    assert service.runs(project.id).list_completed_stages(first.id) == list(DEFAULT_STAGES)
