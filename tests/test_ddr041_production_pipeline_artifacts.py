from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_pipeline_persists_reviewable_and_exportable_quick_episode(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    planner = ProviderConfig(provider_type="fake", default_model="fake-v1")
    speech = ProviderConfig(provider_type="fake-tts")
    config_store.save(
        UserConfig(
            providers={"planner": planner, "speech": speech},
            defaults={"host_generation": "planner:fake-v1"},
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Quick durable workflow")
    root = composition.service.workspaces.project_root(project.id)
    database = composition.database_for_project(project.id)

    episode = composition.service.quick_deep_dive(project.id)
    configs = EpisodeConfigurationService(database)
    quick_config = configs.load_configuration(episode.id)
    episode = configs.edit(episode.id, replace(quick_config, focus="indexed corpus"))
    run = composition.create_generation_run(project.id, episode.id)

    result = composition.run_generation(project.id, run.id)

    with database.connection() as connection:
        turns = connection.execute(
            "SELECT id,text FROM conversation_turns WHERE episode_id=?",
            (episode.id,),
        ).fetchall()
        artifacts = connection.execute(
            "SELECT turn_id,status,path FROM tts_artifacts ORDER BY turn_id"
        ).fetchall()
    output_audio = root / "output" / f"{episode.id}.wav"
    timeline = AudioTimelineRepository(database).get(episode.id)
    export_service = EpisodeLibraryExportService(composition.service.workspaces)
    export = export_service.export(project.id, episode, result.run)

    assert result.run.state == "completed"
    assert turns
    assert "Configured fake provider host turn marker" in str(turns[0]["text"])
    assert artifacts
    assert all(str(row["status"]) == TTS_ARTIFACT_STATUS_COMPLETE for row in artifacts)
    assert output_audio.is_file()
    assert timeline is not None
    assert timeline.placements
    assert export.transcript.is_file()
    transcript = export.transcript.read_text(encoding="utf-8")
    assert "Configured fake provider host turn marker" in transcript
    assert export.audio is not None
    assert export.audio.is_file()
