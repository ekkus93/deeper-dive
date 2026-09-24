from __future__ import annotations

from deeper_dive.composition import ProductionComposition
from deeper_dive.domain.clock import SystemClock, format_timestamp
from deeper_dive.domain.ids import new_run_id
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_composed_deterministic_application_can_plan_and_generate(tmp_path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={
                "episode_planning": "planner:fake-v1",
                "host_generation": "planner:fake-v1",
            },
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Production integration")
    host = create_host_from_preset("skeptic", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    database = composition.database_for_project(project.id)
    episode = EpisodeConfigurationService(database).create(
        project.id,
        EpisodeConfiguration(
            title="Deterministic episode",
            focus="integration",
            target_duration_seconds=1200,
            host_ids=(host.id,),
        ),
    )

    planner = composition.configured_planning_service(project.id, "planner", "fake-v1")
    plan = planner.build_plan(episode.id)

    assert planner.load_plan(episode.id) == plan
    assert plan.target_duration_seconds == 1200

    timestamp = format_timestamp(SystemClock().now())
    run_id = str(new_run_id())
    runs = composition.service.runs(project.id)
    runs.create(
        GenerationRunRecord(
            run_id,
            episode.id,
            "sources",
            "pending",
            timestamp,
            timestamp,
        )
    )
    runner = composition.generation_monitor_controller.runner
    assert runner is not None

    runner(run_id, lambda event: None)

    completed = runs.get(run_id)
    assert completed is not None
    assert completed.state == "completed"
