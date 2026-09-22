from __future__ import annotations

from pathlib import Path

from deeper_dive.audio_timeline import AudioTimelineRepository
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import HostProfileRecord
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_production_pipeline_persists_reviewable_and_exportable_quick_episode(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            }
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Quick durable workflow")
    hosts = composition.service.hosts(project.id)
    hosts.create_host(HostProfileRecord("h1", project.id, "Host One"))

    episode = EpisodeConfigurationService(
        composition.database_for_project(project.id)
    ).create(
        project.id,
        EpisodeConfiguration(
            title="Quick Deep Dive",
            focus="Exercise the normal durable workflow",
            target_duration_seconds=1200,
            host_ids=("h1",),
        ),
    )
    run = composition.create_generation_run(project.id, episode.id)

    result = composition.run_generation(project.id, run.id)

    database = composition.database_for_project(project.id)
    with database.connection() as connection:
        turns = connection.execute(
            "SELECT id,text FROM conversation_turns WHERE episode_id=?",
            (episode.id,),
        ).fetchall()
        artifacts = connection.execute(
            "SELECT turn_id,status,path FROM tts_artifacts ORDER BY turn_id"
        ).fetchall()
    output_audio = (
        composition.service.workspaces.project_root(project.id)
        / "output"
        / f"{episode.id}.wav"
    )
    timeline = AudioTimelineRepository(database).get(episode.id)
    export = EpisodeLibraryExportService(composition.service.workspaces).export(
        project.id,
        episode,
        result.run,
    )

    assert result.run.state == "completed"
    assert turns
    assert "deterministic production turn" in str(turns[0]["text"])
    assert artifacts
    assert all(str(row["status"]) == "completed" for row in artifacts)
    assert output_audio.is_file()
    assert timeline is not None
    assert timeline.placements
    assert export.transcript.is_file()
    assert "deterministic production turn" in export.transcript.read_text(encoding="utf-8")
    assert export.audio is not None
    assert export.audio.is_file()
