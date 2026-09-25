from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive import cli as cli_module
from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _json_call(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _build_project_with_episode(data_dir: Path) -> tuple[ProductionComposition, str, str]:
    UserConfigStore(data_dir / "config.json").save(
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
    project = composition.service.create_project("CLI control")
    episode = composition.service.quick_deep_dive(project.id)
    with composition.database_for_project(project.id).transaction() as connection:
        connection.execute(
            "UPDATE hosts SET tts_provider='speech',tts_voice='voice-a' WHERE project_id=?",
            (project.id,),
        )
    return composition, project.id, episode.id


def test_cli_pause_reaches_durable_paused_state_and_resume_executes_from_checkpoint(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    composition, project_id, episode_id = _build_project_with_episode(data_dir)
    run = composition.create_generation_run(project_id, episode_id)
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    paused = _json_call([*base, "pause", project_id, episode_id], capsys)

    assert paused["id"] == run.id
    assert paused["state"] == "paused"
    persisted_pause = composition.generation_run_repository(project_id).get(run.id)
    assert persisted_pause is not None
    assert persisted_pause.state == "paused"

    resumed = _json_call([*base, "resume", project_id, episode_id], capsys)

    assert resumed["id"] == run.id
    assert resumed["state"] == "completed"
    assert resumed["stage"] == "export"
    root = composition.service.workspaces.project_root(project_id)
    assert (root / "output" / f"{episode_id}.wav").is_file()
    with composition.database_for_project(project_id).connection() as connection:
        turns = connection.execute(
            "SELECT COUNT(*) FROM conversation_turns WHERE episode_id=?",
            (episode_id,),
        ).fetchone()[0]
    assert turns > 0


def test_cli_cancel_reaches_durable_cancelled_state(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    composition, project_id, episode_id = _build_project_with_episode(data_dir)
    run = composition.create_generation_run(project_id, episode_id)
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    cancelled = _json_call([*base, "cancel", project_id, episode_id], capsys)

    assert cancelled["id"] == run.id
    assert cancelled["state"] == "cancelled"
    persisted_cancel = composition.generation_run_repository(project_id).get(run.id)
    assert persisted_cancel is not None
    assert persisted_cancel.state == "cancelled"


def test_cli_rejects_illegal_control_transitions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    composition, project_id, episode_id = _build_project_with_episode(data_dir)
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    completed = _json_call([*base, "generate", project_id, episode_id], capsys)
    assert completed["state"] == "completed"

    assert main([*base, "pause", project_id, episode_id]) == 2
    captured = capsys.readouterr()
    assert "cannot pause generation run in completed state" in captured.err

    assert main([*base, "resume", project_id, episode_id]) == 2
    captured = capsys.readouterr()
    assert "cannot resume generation run in completed state" in captured.err
