"""SPR-07: real CLI lifecycle, restart, and export share durable episode identity."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from deeper_dive.cli import main
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _invoke(
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    *command: str,
) -> tuple[int, object, str]:
    code = main(["--data-dir", str(data_dir), "--json", "episode", *command])
    output = capsys.readouterr()
    return code, json.loads(output.out) if output.out else None, output.err


def test_cli_lifecycle_noop_changed_edit_status_plan_and_export_isolation(
    second_post_review_acceptance,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """CLI uses the same frozen-episode edit guard and historical artifacts as TUI."""
    fixture = second_post_review_acceptance()
    first, second = fixture.completed.first, fixture.completed.second
    service = first.service
    data_dir = service.workspaces.data_dir
    source_digests = {
        item.episode_id: (_digest(item.audio_path), _digest(item.transcript_path))
        for item in (first, second)
    }
    reopened = ProductionComposition.build(data_dir=data_dir)
    for item in (first, second):
        repository = HostEpisodeRepository(reopened.database_for_project(item.project_id))
        before_episode = repository.get_episode(item.episode_id)
        before_plan = repository.get_plan(item.episode_id)
        before_run = reopened.service.runs(item.project_id).get(item.run_id)
        assert before_episode is not None and before_plan is not None
        assert before_run is not None and before_run.state == "completed"

        # Semantically unchanged CLI saves must preserve the plan, run and exports.
        code, payload, error = _invoke(
            data_dir,
            capsys,
            "configure",
            item.project_id,
            item.episode_id,
        )
        assert code == 0 and not error
        assert isinstance(payload, dict)
        assert payload["id"] == item.episode_id
        assert repository.get_episode(item.episode_id) == before_episode
        assert repository.get_plan(item.episode_id) == before_plan

        # Changed configuration must provide the same actionable policy as the service.
        code, payload, error = _invoke(
            data_dir,
            capsys,
            "configure",
            item.project_id,
            item.episode_id,
            "--focus",
            "would corrupt a completed historical episode",
        )
        assert code == 2 and payload is None
        assert "create a new episode" in error
        assert "Traceback" not in error
        assert repository.get_episode(item.episode_id) == before_episode
        assert repository.get_plan(item.episode_id) == before_plan

        code, payload, error = _invoke(
            data_dir, capsys, "show", item.project_id, item.episode_id
        )
        assert code == 0 and not error
        assert payload["episode"]["id"] == item.episode_id
        assert payload["configuration"]["focus"] != "would corrupt a completed historical episode"

        code, payload, error = _invoke(
            data_dir, capsys, "show-plan", item.project_id, item.episode_id
        )
        assert code == 0 and not error
        assert payload["id"] == before_plan.id

        code, payload, error = _invoke(
            data_dir, capsys, "status", item.project_id, item.episode_id
        )
        assert code == 0 and not error
        assert payload["run"]["id"] == item.run_id
        assert payload["run"]["state"] == "completed"

        destination = tmp_path / f"cli-export-{item.episode_id}"
        code, payload, error = _invoke(
            data_dir,
            capsys,
            "export",
            item.project_id,
            item.episode_id,
            "--output-dir",
            str(destination),
        )
        assert code == 0 and not error
        assert payload["episode_id"] == item.episode_id
        assert payload["audio"] and Path(payload["audio"]).is_file()
        assert Path(payload["transcript"]).is_file()
        assert _digest(item.audio_path) == source_digests[item.episode_id][0]
        assert _digest(item.transcript_path) == source_digests[item.episode_id][1]
        assert reopened.service.runs(item.project_id).get(item.run_id) == before_run

    pending_project_id = fixture.pending_project_id
    pending_episode_id = fixture.pending_episode_id
    pending_database = reopened.database_for_project(pending_project_id)
    pending_repo = HostEpisodeRepository(pending_database)
    pending_episode = pending_repo.get_episode(pending_episode_id)
    pending_plan = pending_repo.get_plan(pending_episode_id)
    pending_run = reopened.service.runs(pending_project_id).get(fixture.pending_run_id)
    assert pending_episode is not None and pending_plan is not None
    assert pending_run is not None and pending_run.state == "pending"
    code, payload, error = _invoke(
        data_dir,
        capsys,
        "configure",
        pending_project_id,
        pending_episode_id,
        "--title",
        "invalid edit after pending run",
    )
    assert code == 2 and payload is None
    assert "create a new episode" in error
    assert pending_repo.get_episode(pending_episode_id) == pending_episode
    assert pending_repo.get_plan(pending_episode_id) == pending_plan
    assert reopened.service.runs(pending_project_id).get(fixture.pending_run_id) == pending_run
    assert (data_dir / "config.json").read_bytes() == fixture.config_bytes

    # No pending-run CLI operation may alter either completed project's records.
    for item in (first, second):
        configuration = EpisodeConfigurationService(
            reopened.database_for_project(item.project_id)
        ).load_configuration(item.episode_id)
        assert configuration.focus != "invalid edit after pending run"
        assert (_digest(item.audio_path), _digest(item.transcript_path)) == source_digests[
            item.episode_id
        ]
