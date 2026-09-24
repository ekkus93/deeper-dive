from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_cli_episode_export_uses_shared_artifact_exporter(tmp_path: Path, capsys: object) -> None:
    data_dir = tmp_path / "data"
    config_store = UserConfigStore(data_dir / "config.json")
    config_store.save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={"host_generation": "planner:fake-v1"},
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
    exit_code = main(
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

    assert exit_code == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    exported_paths = {Path(value) for value in payload["paths"]}
    assert exported_paths == {
        Path(payload["transcript"]),
        Path(payload["manifest"]),
        Path(payload["metadata"]),
        Path(payload["audio"]),
    }
    assert {path.parent for path in exported_paths} == {output_dir}
    transcript = Path(payload["transcript"]).read_text(encoding="utf-8")
    assert "deterministic production turn" in transcript
    assert json.loads(Path(payload["manifest"]).read_text(encoding="utf-8")) == {"sources": []}
    metadata = json.loads(Path(payload["metadata"]).read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode.id
    assert metadata["run_id"] == result.run.id
    assert Path(payload["audio"]).read_bytes().startswith(b"FAKE-WAV")
