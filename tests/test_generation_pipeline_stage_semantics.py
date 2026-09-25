from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.pipeline import DEFAULT_STAGES
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_pipeline_export_stage_is_readiness_boundary_not_artifact_export(
    tmp_path: Path,
) -> None:
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
    project = composition.service.create_project("Stage semantics")
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Stage semantics episode",
            focus="Clarify export readiness",
            target_duration_seconds=900,
            host_ids=(host.id,),
        ),
    )
    composition.configured_planning_service(project.id, "planner", "fake-v1").build_plan(episode.id)
    run = composition.create_generation_run(project.id, episode.id)

    completed = composition.run_generation(project.id, run.id).run

    root = composition.service.workspaces.project_root(project.id)
    export_root = root / "exports"
    repository = composition.generation_run_repository(project.id)
    assert completed.state == "completed"
    assert completed.stage == "export"
    assert repository.list_completed_stages(completed.id) == list(DEFAULT_STAGES)
    assert not export_root.exists()

    exported = EpisodeLibraryExportService(composition.service.workspaces).export(
        project.id,
        episode,
        completed,
        output_dir=export_root,
    )

    assert exported.transcript.is_file()
    assert exported.manifest.is_file()
    assert exported.metadata.is_file()
    assert exported.audio is not None
    assert exported.audio.is_file()
    metadata = json.loads(exported.metadata.read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["run_id"] == completed.id
