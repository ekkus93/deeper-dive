from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_shared_episode_export_supports_cli_selected_output_directory(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    config_store.save(
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
    project = composition.service.create_project("CLI export")
    episode = composition.service.quick_deep_dive(project.id)
    configs = EpisodeConfigurationService(composition.database_for_project(project.id))
    config = configs.load_configuration(episode.id)
    configs.edit(episode.id, replace(config, focus="focused deep dive"))
    run = composition.create_generation_run(project.id, episode.id)
    result = composition.run_generation(project.id, run.id)
    assert result.run.state == "completed"

    output_dir = tmp_path / "cli-exports"
    exported = EpisodeLibraryExportService(composition.service.workspaces).export(
        project.id,
        episode,
        result.run,
        output_dir=output_dir,
    )

    assert {path.parent for path in exported.paths} == {output_dir}
    assert "deterministic production turn" in exported.transcript.read_text(encoding="utf-8")
    assert json.loads(exported.manifest.read_text(encoding="utf-8")) == []
    metadata = json.loads(exported.metadata.read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["run_id"] == result.run.id
    assert exported.audio is not None
    assert exported.audio.read_bytes().startswith(b"FAKE-WAV")
