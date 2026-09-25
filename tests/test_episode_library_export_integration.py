from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController, EpisodeLibraryItem
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.run_repositories import GenerationRunRecord
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_library_export_creates_episode_specific_artifacts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "tts": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={"host_generation": "planner:fake-v1"},
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Library export")
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "tts"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Exported episode",
            focus="Exercise library export",
            target_duration_seconds=900,
            host_ids=(host.id,),
        ),
    )
    composition.configured_planning_service(project.id, "planner", "fake-v1").build_plan(episode.id)
    run = composition.create_generation_run(project.id, episode.id)
    completed = composition.run_generation(project.id, run.id).run

    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id
    result = EpisodeLibraryController.export(app, EpisodeLibraryItem(episode, completed))

    assert result.transcript.is_file()
    assert result.manifest.is_file()
    assert result.metadata.is_file()
    assert result.audio is not None
    assert result.audio.is_file()
    assert episode.id in result.transcript.name
    assert episode.id in result.audio.name
    assert "Configured fake provider host turn marker" in result.transcript.read_text(
        encoding="utf-8"
    )
    metadata = json.loads(result.metadata.read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["run_id"] == completed.id
    assert result.audio.read_bytes().startswith(b"FAKE-WAV")


def test_library_export_targets_selected_episode_run_identity(tmp_path: Path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Library export identity")
    config_service = EpisodeConfigurationService(composition.database_for_project(project.id))
    first = config_service.create(project.id, EpisodeConfiguration(title="First"))
    second = config_service.create(project.id, EpisodeConfiguration(title="Second"))
    repository = composition.generation_run_repository(project.id)
    first_run = GenerationRunRecord("run-first", first.id, "export", "completed", "t", "t")
    second_run = GenerationRunRecord("run-second", second.id, "export", "completed", "t", "t")
    repository.create(first_run)
    repository.create(second_run)
    root = composition.service.workspaces.project_root(project.id)
    output = root / "output"
    output.mkdir(parents=True, exist_ok=True)
    (output / f"{first.id}.wav").write_bytes(b"audio-first")
    (output / f"{second.id}.wav").write_bytes(b"audio-second")
    database = composition.database_for_project(project.id)
    with database.transaction() as connection:
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-first", first.id, 0, 0, "host-first", "first transcript", "[]"),
        )
        connection.execute(
            """INSERT INTO conversation_turns(
                id,episode_id,segment_ordinal,turn_ordinal,speaker_id,text,evidence_ids_json
            ) VALUES (?,?,?,?,?,?,?)""",
            ("turn-second", second.id, 0, 0, "host-second", "second transcript", "[]"),
        )
    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id
    app.current_episode_id = second.id
    app.current_run_id = second_run.id

    result = EpisodeLibraryController.export(app, EpisodeLibraryItem(first, first_run))

    metadata = json.loads(result.metadata.read_text(encoding="utf-8"))
    assert metadata["episode_id"] == first.id
    assert metadata["run_id"] == first_run.id
    assert first.id in result.transcript.name
    assert result.audio is not None
    assert first.id in result.audio.name
    assert result.audio.read_bytes() == b"audio-first"
    assert "first transcript" in result.transcript.read_text(encoding="utf-8")
    assert "second transcript" not in result.transcript.read_text(encoding="utf-8")


def test_library_resume_targets_selected_episode_run_identity(tmp_path: Path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Library resume identity")
    config_service = EpisodeConfigurationService(composition.database_for_project(project.id))
    first = config_service.create(project.id, EpisodeConfiguration(title="First"))
    second = config_service.create(project.id, EpisodeConfiguration(title="Second"))
    repository = composition.generation_run_repository(project.id)
    first_run = composition.create_generation_run(project.id, first.id)
    second_run = composition.create_generation_run(project.id, second.id)
    repository.update(replace(first_run, state="paused"))
    repository.update(replace(second_run, state="paused"))
    paused_first = repository.get(first_run.id)
    assert paused_first is not None
    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id
    app.current_episode_id = second.id
    app.current_run_id = second_run.id

    resumed = EpisodeLibraryController.resume(app, EpisodeLibraryItem(first, paused_first))

    assert resumed.id == first_run.id
    assert resumed.episode_id == first.id
    assert resumed.state == "pending"
    assert app.current_episode_id == first.id
    assert app.current_run_id == first_run.id
    assert repository.get(second_run.id) is not None
    assert repository.get(first_run.id) == resumed


def test_library_export_rejects_incomplete_episode(tmp_path: Path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data",
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Incomplete library export")
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(title="Incomplete episode"),
    )
    run = composition.create_generation_run(project.id, episode.id)
    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id

    try:
        EpisodeLibraryController.export(app, EpisodeLibraryItem(episode, run))
    except ValueError as exc:
        assert "not exportable" in str(exc)
    else:
        raise AssertionError("incomplete episode export unexpectedly succeeded")
