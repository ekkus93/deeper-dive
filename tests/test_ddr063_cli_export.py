from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_cli_export_uses_shared_episode_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
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
    assert (
        main(
            [
                "--data-dir",
                str(data_dir),
                "--json",
                "episode",
                "export",
                project.id,
                episode.id,
                "--output-dir",
                str(output_dir),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["episode_id"] == episode.id
    transcript = Path(payload["transcript"])
    manifest = Path(payload["manifest"])
    metadata = Path(payload["metadata"])
    audio = Path(payload["audio"])
    assert {path.parent for path in (transcript, manifest, metadata, audio)} == {output_dir}
    assert "deterministic production turn" in transcript.read_text(encoding="utf-8")
    assert json.loads(manifest.read_text(encoding="utf-8")) == []
    metadata_payload = json.loads(metadata.read_text(encoding="utf-8"))
    assert metadata_payload["episode_id"] == episode.id
    assert metadata_payload["run_id"] == result.run.id
    assert audio.read_bytes().startswith(b"FAKE-WAV")
