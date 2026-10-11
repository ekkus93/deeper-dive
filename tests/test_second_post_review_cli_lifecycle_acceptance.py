"""CLI lifecycle and export acceptance against the shared production fixture.

These tests intentionally use the installed CLI's public command dispatcher and
production service composition, rather than seeding database rows or mocking
episode state. They also exercise multi-project artifact isolation.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from deeper_dive.cli import main
from tests.conftest import SecondPostReviewAcceptance, TwoProjectCompletedAcceptance


def _cli(
    data_dir: Path,
    capsys: pytest.CaptureFixture[str],
    *args: str,
) -> tuple[int, Any, str]:
    result = main(["--data-dir", str(data_dir), "--json", *args])
    captured = capsys.readouterr()
    payload: Any = json.loads(captured.out) if captured.out.strip() else None
    return result, payload, captured.err


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_completed_episodes_cli_status_plan_noop_edit_export_and_isolation(
    two_project_completed_acceptance: Callable[[], TwoProjectCompletedAcceptance],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = two_project_completed_acceptance()
    capsys.readouterr()
    data_dir = fixture.first.service.workspaces.data_dir
    completed = (fixture.first, fixture.second)
    for index, episode in enumerate(completed):
        code, listing, err = _cli(data_dir, capsys, "episode", "list", episode.project_id)
        assert code == 0, err
        assert [item["id"] for item in listing] == [episode.episode_id]

        code, shown, err = _cli(
            data_dir, capsys, "episode", "show", episode.project_id, episode.episode_id
        )
        assert code == 0, err
        assert shown["episode"]["id"] == episode.episode_id
        assert shown["episode"]["state"] == "completed"

        code, plan, err = _cli(
            data_dir, capsys, "episode", "show-plan", episode.project_id, episode.episode_id
        )
        assert code == 0, err
        assert plan["episode_id"] == episode.episode_id

        code, status, err = _cli(
            data_dir, capsys, "episode", "status", episode.project_id, episode.episode_id
        )
        assert code == 0, err
        assert status["run"]["id"] == episode.run_id
        assert status["run"]["state"] == "completed"

        # A semantically identical edit must not demote a completed episode,
        # update its revision, or invalidate the historical plan.
        code, unchanged, err = _cli(
            data_dir, capsys, "episode", "configure", episode.project_id, episode.episode_id
        )
        assert code == 0, err
        assert unchanged == shown["episode"]

        code, changed, err = _cli(
            data_dir,
            capsys,
            "episode",
            "configure",
            episode.project_id,
            episode.episode_id,
            "--title",
            "Attempted rewrite of a completed episode",
        )
        assert code == 2
        assert changed is None
        assert "create a new episode" in err

        code, still_plan, err = _cli(
            data_dir, capsys, "episode", "show-plan", episode.project_id, episode.episode_id
        )
        assert code == 0, err
        assert still_plan == plan

        output_dir = tmp_path / f"cli-export-{index}"
        code, exported, err = _cli(
            data_dir,
            capsys,
            "episode",
            "export",
            episode.project_id,
            episode.episode_id,
            "--output-dir",
            str(output_dir),
        )
        assert code == 0, err
        assert exported["episode_id"] == episode.episode_id
        assert _digest(Path(exported["audio"])) == _digest(episode.audio_path)
        assert _digest(Path(exported["transcript"])) == _digest(episode.transcript_path)
        metadata = json.loads(Path(exported["metadata"]).read_text(encoding="utf-8"))
        assert metadata["project_id"] == episode.project_id
        assert metadata["episode_id"] == episode.episode_id
        assert metadata["run_id"] == episode.run_id

        foreign = completed[1 - index]
        code, result, err = _cli(
            data_dir, capsys, "episode", "show", episode.project_id, foreign.episode_id
        )
        assert code == 2
        assert result is None
        assert "episode not found" in err


def test_pending_run_cli_rejects_export_and_configuration_change_without_mutation(
    second_post_review_acceptance: Callable[[], SecondPostReviewAcceptance],
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = second_post_review_acceptance()
    capsys.readouterr()
    data_dir = fixture.completed.first.service.workspaces.data_dir
    project_id = fixture.pending_project_id
    episode_id = fixture.pending_episode_id

    code, before, err = _cli(data_dir, capsys, "episode", "show", project_id, episode_id)
    assert code == 0, err
    code, status, err = _cli(data_dir, capsys, "episode", "status", project_id, episode_id)
    assert code == 0, err
    assert status["run"]["id"] == fixture.pending_run_id
    assert status["run"]["state"] == "pending"

    code, output, err = _cli(data_dir, capsys, "episode", "export", project_id, episode_id)
    assert code == 2
    assert output is None
    assert "not exportable" in err

    code, output, err = _cli(
        data_dir,
        capsys,
        "episode",
        "configure",
        project_id,
        episode_id,
        "--title",
        "Cannot edit a pending generation",
    )
    assert code == 2
    assert output is None

    code, after, err = _cli(data_dir, capsys, "episode", "show", project_id, episode_id)
    assert code == 0, err
    assert after == before
    code, still_pending, err = _cli(data_dir, capsys, "episode", "status", project_id, episode_id)
    assert code == 0, err
    assert still_pending == status
