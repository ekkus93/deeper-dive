from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


def test_tui_acceptance_click_generate_review_and_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asyncio.run(_exercise_tui_acceptance(tmp_path, monkeypatch))


async def _exercise_tui_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("DDR-112 TUI")
    service.add_pasted_source(
        project.id,
        "Corpus",
        "Deterministic grounded source text for the TUI acceptance workflow.",
    )
    hosts = service.hosts(project.id)
    for host_id, name in (("h1", "Host One"), ("h2", "Host Two")):
        hosts.create_host(
            HostProfile(
                host_id,
                project.id,
                name,
                tts_provider="fake-tts",
                tts_voice="voice-a",
            ).to_record()
        )

    controller = _provider_controller(service)
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("deterministic ffmpeg readiness marker", encoding="utf-8")
    app = DeeperDiveApp(
        service,
        provider_controller=controller,
        preflight_controller=PreflightController(ffmpeg_executable=fake_ffmpeg),
    )
    monkeypatch.setattr(
        GenerationMonitorScreen,
        "start_background_generation",
        lambda self: None,
    )

    async with app.run_test(size=(120, 50)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        app.screen.action_quick_deep_dive()
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        assert app.preflight_controller.build(app).report.ready

        await pilot.click("#action-generate")
        await pilot.pause()
        assert isinstance(app.screen, GenerationMonitorScreen)
        monitor = app.screen
        before = app.generation_monitor_controller.snapshot(app)
        assert before.run is not None
        assert before.run.state == "pending"

        composition = app.service._production_composition
        composition.run_generation(project.id, before.run.id)
        monitor.refresh_monitor()
        after = app.generation_monitor_controller.snapshot(app)
        assert after.run is not None
        assert after.run.state == "completed"
        assert after.run.stage == "export"
        assert after.completed_stages
        assert TranscriptReviewController().turns(app)

        app.action_navigate("library")
        await pilot.pause()
        item = EpisodeLibraryController.items(app)[0]
        exported = EpisodeLibraryController.export(app, item)
        assert exported.paths
        assert all(path.is_file() for path in exported.paths)


def _provider_controller(service: DeeperDiveService) -> ProviderController:
    registry = LLMProviderRegistry()
    registry.register(
        FakeLLMProvider(
            model="fake-v1",
            response=(
                '{"segments":[{"title":"Acceptance","purpose":"Explain evidence",'
                '"target_duration_seconds":1200,"lead_host_ids":[]}]}'
            ),
        )
    )
    store = UserConfigStore(service.workspaces.data_dir / "config.json")
    config = store.load()
    for role in ModelRole:
        config.defaults[role.value] = "fake:fake-v1"
    store.save(config)
    controller = ProviderController(store, registry, {})
    controller.tts_providers["fake-tts"] = FakeTTSProvider(provider_id="fake-tts")
    return controller
