from __future__ import annotations

import asyncio
import json
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.episode_planner import EpisodePlannerService
from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelRole
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfig, UserConfigStore


def _episode_host_presets(
    service: DeeperDiveService, project_id: str, host_ids: tuple[str, ...]
) -> tuple[str | None, ...]:
    hosts = {host.id: host for host in service.hosts(project_id).list_hosts(project_id)}
    return tuple(hosts[host_id].preset_origin for host_id in host_ids)


def test_quick_deep_dive_creates_normal_episode_with_default_hosts_and_useful_policy(
    tmp_path: Path,
) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick")

    episode = service.quick_deep_dive(project.id)

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    policy = ResearchPolicyStore(database).episode(project.id, episode.id)
    assert config.title == "Quick Deep Dive"
    assert config.target_duration_seconds == 1200
    assert config.research_overrides["policy"] == "useful"
    assert _episode_host_presets(service, project.id, config.host_ids) == (
        "curious_explainer",
        "skeptic",
    )
    assert policy.mode is ResearchMode.USEFUL


def test_quick_deep_dive_uses_existing_project_hosts_as_defaults(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick with hosts")
    service.hosts(project.id).create_host(HostProfile("h1", project.id, "Existing One").to_record())
    service.hosts(project.id).create_host(HostProfile("h2", project.id, "Existing Two").to_record())
    service.hosts(project.id).create_host(
        HostProfile("h3", project.id, "Existing Three").to_record()
    )

    episode = service.quick_deep_dive(project.id)

    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.host_ids == ("h1", "h3")
    assert len(service.hosts(project.id).list_hosts(project.id)) == 3


def test_quick_deep_dive_user_defaults_override_builtins(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick configured")
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            defaults={
                "quick_deep_dive_duration_minutes": "12",
                "quick_deep_dive_host_presets": "skeptic,curious_explainer",
                "quick_deep_dive_research_policy": "off",
            }
        )
    )

    episode = service.quick_deep_dive(project.id)
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.target_duration_seconds == 720
    assert config.research_overrides["policy"] == "off"
    assert _episode_host_presets(service, project.id, config.host_ids) == (
        "skeptic",
        "curious_explainer",
    )


def test_quick_deep_dive_project_overrides_take_precedence(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project(
        "Quick project override",
        instructions=json.dumps(
            {
                "quick_deep_dive": {
                    "duration_minutes": 7,
                    "host_presets": "curious_explainer,skeptic",
                    "research_policy": "useful",
                }
            }
        ),
    )
    UserConfigStore(service.workspaces.data_dir / "config.json").save(
        UserConfig(
            defaults={
                "quick_deep_dive_duration_minutes": "12",
                "quick_deep_dive_host_presets": "skeptic,curious_explainer",
                "quick_deep_dive_research_policy": "off",
            }
        )
    )

    episode = service.quick_deep_dive(project.id)
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    config = EpisodeConfigurationService(database).load_configuration(episode.id)
    assert config.target_duration_seconds == 420
    assert config.research_overrides["policy"] == "useful"
    assert _episode_host_presets(service, project.id, config.host_ids) == (
        "curious_explainer",
        "skeptic",
    )


def test_quick_deep_dive_tui_action_builds_durable_plan_and_reaches_preflight(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_quick_tui(tmp_path))


async def _exercise_quick_tui(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick TUI")
    controller = _planning_provider_controller(service)
    app = DeeperDiveApp(service, provider_controller=controller)
    async with app.run_test(size=(100, 40)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        app.screen.action_quick_deep_dive()
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        assert app.current_episode_id is not None

    episode = service.hosts(project.id).list_episodes(project.id)[0]
    assert episode.title == "Quick Deep Dive"
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    plan = EpisodePlannerService(database, _unused_generator()).load_plan(episode.id)
    assert len(plan.segments) == 1
    assert plan.segments[0].title == "Quick Opening"


def test_quick_deep_dive_preflight_executes_pipeline_and_exports_artifacts(
    tmp_path: Path,
) -> None:
    asyncio.run(_exercise_quick_generation_tui(tmp_path))


async def _exercise_quick_generation_tui(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Quick Generate")
    service.add_pasted_source(
        project.id,
        "Corpus",
        "Grounded source text that should be indexed before quick generation.",
    )
    hosts = service.hosts(project.id)
    hosts.create_host(
        HostProfile(
            "h1",
            project.id,
            "Existing One",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    hosts.create_host(
        HostProfile(
            "h2",
            project.id,
            "Existing Two",
            tts_provider="fake-tts",
            tts_voice="voice-a",
        ).to_record()
    )
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.write_text("fake ffmpeg marker", encoding="utf-8")
    app = DeeperDiveApp(
        service,
        provider_controller=_generation_provider_controller(service),
        preflight_controller=PreflightController(ffmpeg_executable=fake_ffmpeg),
    )

    async with app.run_test(size=(120, 50)) as pilot:
        app.current_project_id = project.id
        app.current_project_name = project.name
        app.action_navigate("episode")
        await pilot.pause()
        app.screen.action_quick_deep_dive()
        await pilot.pause()
        assert isinstance(app.screen, PreflightScreen)
        presentation = app.preflight_controller.build(app)
        assert presentation.report.ready
        run = app.preflight_controller.start_generation(app)
        composition = app.service._production_composition
        composition.run_generation(project.id, run.id)
        await pilot.pause()

    episode = hosts.list_episodes(project.id)[0]
    run = service.runs(project.id).latest_for_episode(episode.id)
    assert run is not None
    assert run.state == "completed"
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    with database.connection() as connection:
        turn_count = connection.execute(
            "SELECT COUNT(*) FROM conversation_turns WHERE episode_id=?", (episode.id,)
        ).fetchone()[0]
        audio_count = connection.execute("SELECT COUNT(*) FROM tts_artifacts").fetchone()[0]
    assert turn_count > 0
    assert audio_count > 0
    assert AudioTimelineRepository(database).get(episode.id) is not None
    assert (service.workspaces.project_root(project.id) / "output" / f"{episode.id}.wav").is_file()
    app.current_project_id = project.id
    app.current_episode_id = episode.id
    app.current_run_id = run.id
    assert TranscriptReviewController().turns(app)
    item = EpisodeLibraryController.items(app)[0]
    export = EpisodeLibraryController.export(app, item)
    assert export.paths
    assert all(path.is_file() for path in export.paths)


def _planning_provider_controller(service: DeeperDiveService) -> ProviderController:
    registry = LLMProviderRegistry()
    registry.register(
        FakeLLMProvider(
            model="fake-v1",
            response=(
                '{"segments":[{"title":"Quick Opening","purpose":"Explain evidence",'
                '"target_duration_seconds":1200,"lead_host_ids":[]}]}'
            ),
        )
    )
    store = UserConfigStore(service.workspaces.data_dir / "config.json")
    config = store.load()
    config.defaults["episode_planning"] = "fake:fake-v1"
    store.save(config)
    return ProviderController(store, registry, {})


def _generation_provider_controller(service: DeeperDiveService) -> ProviderController:
    controller = _planning_provider_controller(service)
    config = controller.config()
    for role in ModelRole:
        config.defaults[role.value] = "fake:fake-v1"
    controller.config_store.save(config)
    controller.tts_providers["fake-tts"] = FakeTTSProvider(provider_id="fake-tts")
    return controller


def _unused_generator():
    class UnusedGenerator:
        def generate_plan(self, request):  # pragma: no cover
            raise AssertionError("persisted Quick Deep Dive plan should be loaded")

    return UnusedGenerator()
