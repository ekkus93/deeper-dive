from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.transcript_review_screen import TranscriptReviewController
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_multi_episode_review_playback_and_export_artifacts_are_isolated(tmp_path: Path) -> None:
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
    project = composition.service.create_project("Isolation matrix")
    database = composition.database_for_project(project.id)
    configs = EpisodeConfigurationService(database)

    first = composition.service.quick_deep_dive(project.id)
    first_config = configs.load_configuration(first.id)
    first = configs.edit(
        first.id,
        replace(first_config, title="First isolated episode", focus="first focus"),
    )
    second = composition.service.quick_deep_dive(project.id)
    second_config = configs.load_configuration(second.id)
    second = configs.edit(
        second.id,
        replace(second_config, title="Second isolated episode", focus="second focus"),
    )
    with database.transaction() as connection:
        connection.execute(
            "UPDATE hosts SET tts_provider='speech',tts_voice='voice-a' WHERE project_id=?",
            (project.id,),
        )

    first_run = composition.run_generation(
        project.id,
        composition.create_generation_run(project.id, first.id).id,
    ).run
    second_run = composition.run_generation(
        project.id,
        composition.create_generation_run(project.id, second.id).id,
    ).run

    assert first_run.state == "completed"
    assert second_run.state == "completed"
    assert first_run.episode_id == first.id
    assert second_run.episode_id == second.id

    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id
    review = TranscriptReviewController()

    app.current_episode_id = first.id
    first_turns = review.turns(app)
    first_audio = review.audio_path(app)
    first_review_export = review.export_markdown(app)

    app.current_episode_id = second.id
    second_turns = review.turns(app)
    second_audio = review.audio_path(app)
    second_review_export = review.export_markdown(app)

    assert first_turns
    assert second_turns
    assert {turn.id for turn in first_turns}.isdisjoint({turn.id for turn in second_turns})
    assert first_audio is not None
    assert second_audio is not None
    assert first_audio.name == f"{first.id}.wav"
    assert second_audio.name == f"{second.id}.wav"
    assert first_audio != second_audio
    assert first_review_export.name == f"{first.id}-transcript-review.md"
    assert second_review_export.name == f"{second.id}-transcript-review.md"
    assert first.id in first_review_export.read_text(encoding="utf-8")
    assert second.id in second_review_export.read_text(encoding="utf-8")

    exporter = EpisodeLibraryExportService(composition.service.workspaces)
    output_dir = tmp_path / "exports"
    first_export = exporter.export(project.id, first, first_run, output_dir=output_dir)
    second_export = exporter.export(project.id, second, second_run, output_dir=output_dir)

    assert set(first_export.paths).isdisjoint(set(second_export.paths))
    assert first.id in first_export.transcript.name
    assert second.id in second_export.transcript.name
    assert first.id in first_export.audio.name if first_export.audio is not None else False
    assert second.id in second_export.audio.name if second_export.audio is not None else False

    first_metadata = json.loads(first_export.metadata.read_text(encoding="utf-8"))
    second_metadata = json.loads(second_export.metadata.read_text(encoding="utf-8"))
    assert first_metadata["episode_id"] == first.id
    assert second_metadata["episode_id"] == second.id
    assert first_metadata["run_id"] == first_run.id
    assert second_metadata["run_id"] == second_run.id
    assert first_export.audio is not None
    assert second_export.audio is not None
    assert first_export.audio.read_bytes().startswith(b"RIFF")
    assert second_export.audio.read_bytes().startswith(b"RIFF")
