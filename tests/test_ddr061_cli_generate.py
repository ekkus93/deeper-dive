from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive import cli as cli_module
from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tts_generation import TTS_ARTIFACT_STATUS_COMPLETE
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_cli_generate_reaches_completed_state_and_persists_episode_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
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
    project = composition.service.create_project("CLI generate")
    composition.service.add_pasted_source(project.id, "Fixture source", "Deterministic source text.")
    episode = composition.service.quick_deep_dive(project.id)
    database = composition.database_for_project(project.id)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE hosts SET tts_provider='speech',tts_voice='voice-a' WHERE project_id=?",
            (project.id,),
        )
    configs = EpisodeConfigurationService(database)
    config = configs.load_configuration(episode.id)
    configs.edit(episode.id, replace(config, focus="focused deep dive"))
    monkeypatch.setattr(
        "deeper_dive.preflight.FFmpegConfig.detect",
        staticmethod(lambda executable=None: executable or Path("/fake/ffmpeg")),

    )
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )

    assert (
        main(
            [
                "--data-dir",
                str(data_dir),
                "--json",
                "episode",
                "generate",
                project.id,
                episode.id,
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "completed"
    assert payload["episode_id"] == episode.id
    assert payload["stage"] == "export"
    run = composition.generation_run_repository(project.id).get(str(payload["id"]))
    assert run is not None
    assert run.state == "completed"
    with database.connection() as connection:
        turns = connection.execute(
            "SELECT text FROM conversation_turns WHERE episode_id=?",
            (episode.id,),
        ).fetchall()
        artifacts = connection.execute(
            "SELECT status,path FROM tts_artifacts ORDER BY turn_id"
        ).fetchall()
    assert turns
    assert "Configured fake provider host turn marker" in str(turns[0]["text"])
    assert artifacts
    assert all(str(row["status"]) == TTS_ARTIFACT_STATUS_COMPLETE for row in artifacts)
    assert all(Path(str(row["path"])).is_file() for row in artifacts)
    root = composition.service.workspaces.project_root(project.id)
    assert (root / "output" / f"{episode.id}.wav").is_file()
