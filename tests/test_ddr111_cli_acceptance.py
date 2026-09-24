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


def test_cli_acceptance_create_source_host_episode_generate_export(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"planner": ProviderConfig(provider_type="fake", default_model="fake-v1")},
            defaults={"episode_planning": "planner:fake-v1"},
        )
    )
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("Deterministic local acceptance corpus about orbital mechanics.", encoding="utf-8")
    base = ["--data-dir", str(data_dir), "--json"]

    project = _json_call([*base, "project", "create", "DDR-111 acceptance"], capsys)
    project_id = str(project["id"])
    added = _json_call([*base, "source", "add", project_id, str(corpus)], capsys)
    assert added["imported"]
    host = _json_call([*base, "host", "create", project_id, "curious_explainer"], capsys)
    episode = _json_call(
        [
            *base,
            "episode",
            "create",
            project_id,
            "--title",
            "Acceptance episode",
            "--hosts",
            str(host["id"]),
            "--duration",
            "900",
        ],
        capsys,
    )
    episode_id = str(episode["id"])
    plan = _json_call([*base, "episode", "plan", project_id, episode_id], capsys)
    assert plan["episode_id"] == episode_id

    generated = _json_call([*base, "episode", "generate", project_id, episode_id], capsys)
    assert generated["state"] == "completed"
    status = _json_call([*base, "episode", "status", project_id, episode_id], capsys)
    assert status["run"]["state"] == "completed"

    exported = _json_call(
        [
            *base,
            "episode",
            "export",
            project_id,
            episode_id,
            "--output-dir",
            str(tmp_path / "exports"),
        ],
        capsys,
    )
    paths = [Path(str(path)) for path in exported["paths"]]
    assert paths and all(path.is_file() for path in paths)
    assert Path(str(exported["audio"])).read_bytes().startswith(b"FAKE-WAV")
    metadata = json.loads(Path(str(exported["metadata"])).read_text(encoding="utf-8"))
    assert metadata["episode_id"] == episode_id
    assert metadata["run_id"] == generated["id"]


def test_cli_acceptance_pause_resume_uses_durable_control_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "data"
    composition = ProductionComposition.build(data_dir, provider_factory=ProviderFactory(environ={}))
    project = composition.service.create_project("DDR-111 control")
    episode = composition.service.quick_deep_dive(project.id)
    run = composition.create_generation_run(project.id, episode.id)
    monkeypatch.setattr(
        cli_module.ProductionComposition,
        "build",
        staticmethod(lambda data_dir=None: composition),
    )
    base = ["--data-dir", str(data_dir), "--json", "episode"]

    paused = _json_call([*base, "pause", project.id, episode.id], capsys)
    assert paused["id"] == run.id
    assert paused["state"] == "paused"
    resumed = _json_call([*base, "resume", project.id, episode.id], capsys)
    assert resumed["id"] == run.id
    assert resumed["state"] == "completed"

    persisted = composition.generation_run_repository(project.id).get(run.id)
    assert persisted is not None
    assert persisted.state == "completed"
    assert (composition.service.workspaces.project_root(project.id) / "output" / f"{episode.id}.wav").is_file()
