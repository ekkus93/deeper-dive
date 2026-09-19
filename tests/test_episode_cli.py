from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.cli import main


def _json_call(args: list[str], capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _json_list(args: list[str], capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def test_episode_cli_create_plan_run_control_status_and_export(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = ["--data-dir", str(tmp_path), "--json"]
    project = _json_call([*base, "project", "create", "Episode CLI"], capsys)
    project_id = str(project["id"])
    host = _json_call([*base, "host", "create", project_id, "curious_explainer"], capsys)
    host_id = str(host["id"])

    episode = _json_call(
        [
            *base,
            "episode",
            "create",
            project_id,
            "--title",
            "CLI Episode",
            "--focus",
            "Explain the fixture corpus",
            "--duration",
            "900",
            "--hosts",
            host_id,
            "--research-policy",
            "useful",
        ],
        capsys,
    )
    episode_id = str(episode["id"])
    assert episode["title"] == "CLI Episode"

    episodes = _json_list([*base, "episode", "list", project_id], capsys)
    assert [item["id"] for item in episodes] == [episode_id]

    shown = _json_call([*base, "episode", "show", project_id, episode_id], capsys)
    assert shown["configuration"]["host_ids"] == [host_id]
    assert shown["configuration"]["research_overrides"]["policy"] == "useful"

    configured = _json_call(
        [*base, "episode", "configure", project_id, episode_id, "--style", "roundtable"],
        capsys,
    )
    assert configured["style"] == "roundtable"

    plan = _json_call([*base, "episode", "plan", project_id, episode_id], capsys)
    assert plan["episode_id"] == episode_id
    assert plan["segments"][0]["target_duration_seconds"] == 900

    shown_plan = _json_call([*base, "episode", "show-plan", project_id, episode_id], capsys)
    assert shown_plan["id"] == plan["id"]

    run = _json_call([*base, "episode", "generate", project_id, episode_id], capsys)
    assert run["episode_id"] == episode_id
    assert run["state"] == "pending"

    paused = _json_call([*base, "episode", "pause", project_id, episode_id], capsys)
    assert paused["pause_requested"] is True

    status = _json_call([*base, "episode", "status", project_id, episode_id], capsys)
    assert status["run"]["id"] == run["id"]
    assert status["run"]["pause_requested"] is True

    resumed = _json_call([*base, "episode", "resume", project_id, episode_id], capsys)
    assert resumed["state"] == "pending"
    assert resumed["pause_requested"] is False

    cancelled = _json_call([*base, "episode", "cancel", project_id, episode_id], capsys)
    assert cancelled["cancel_requested"] is True

    export = _json_call(
        [*base, "episode", "export", project_id, episode_id, "--output-dir", str(tmp_path / "exports")],
        capsys,
    )
    export_path = Path(str(export["path"]))
    assert export_path.is_file()
    exported = json.loads(export_path.read_text())
    assert exported["episode"]["id"] == episode_id
    assert exported["plan"]["id"] == plan["id"]
    assert exported["run"]["id"] == run["id"]
