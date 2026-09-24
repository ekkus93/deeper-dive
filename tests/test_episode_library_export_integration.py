from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController, EpisodeLibraryItem
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_library_export_creates_episode_specific_artifacts(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"planner": ProviderConfig(provider_type="fake", default_model="fake-v1")},
            defaults={"host_generation": "planner:fake-v1"},
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Library export")
    host = create_host_from_preset("curious_explainer", project.id)
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
