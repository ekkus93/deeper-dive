"""5PR-02: a stopping run the CLI could not reach no longer blocks generation forever."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_generation_start import _episode

from deeper_dive.cli import main
from deeper_dive.generation_start import select_or_create_generation_run
from deeper_dive.storage.episode_errors import GenerationRunStillStopping
from deeper_dive.storage.run_repositories import GenerationRunRecord


def _run(run_id: str, episode_id: str, state: str, created: str, **flags) -> GenerationRunRecord:  # type: ignore[no-untyped-def]
    return GenerationRunRecord(run_id, episode_id, "sources", state, created, created, **flags)


def _states(service, project_id: str, episode_id: str) -> dict[str, tuple[str, bool]]:  # type: ignore[no-untyped-def]
    with service.hosts(project_id).database.connection() as db:
        rows = db.execute(
            "SELECT id,state,cancel_requested FROM generation_runs WHERE episode_id=?",
            (episode_id,),
        ).fetchall()
    return {row["id"]: (row["state"], bool(row["cancel_requested"])) for row in rows}


def _legacy_database(tmp_path: Path):  # type: ignore[no-untyped-def]
    """r1 running + cancel-requested (worker gone), newer r2 pending (written before FPR-06)."""

    service, project_id, episode_id = _episode(tmp_path)
    runs = service.runs(project_id)
    runs.create(_run("r1", episode_id, "running", "2026-01-01T00:00:00Z", cancel_requested=True))
    runs.create(_run("r2", episode_id, "pending", "2026-01-02T00:00:00Z"))
    return service, project_id, episode_id


def _cancel(tmp_path: Path, project_id: str, episode_id: str, *extra: str) -> int:
    return main(
        ["--data-dir", str(tmp_path / "data"), "--json", "episode", "cancel", project_id]
        + [episode_id, *extra]
    )


def test_refusal_names_the_blocking_run_and_the_command(tmp_path: Path) -> None:
    service, project_id, episode_id = _legacy_database(tmp_path)
    with pytest.raises(GenerationRunStillStopping) as raised:
        select_or_create_generation_run(service, project_id, episode_id)
    message = str(raised.value)
    assert "r1" in message
    assert "episode cancel" in message
    assert "--run r1" in message


def test_cli_cancel_reaches_the_blocking_run_and_start_then_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    service, project_id, episode_id = _legacy_database(tmp_path)

    assert _cancel(tmp_path, project_id, episode_id) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "r1"
    states = _states(service, project_id, episode_id)
    assert states["r1"][0] == "cancelled"
    # r2 was not touched by the cancel.
    assert states["r2"] == ("pending", False)
    result = select_or_create_generation_run(service, project_id, episode_id)
    assert result.run.id == "r2" and not result.created
    active = [s for s, _ in _states(service, project_id, episode_id).values() if s == "pending"]
    assert len(active) == 1


def test_cli_cancel_run_option_selects_a_specific_run(tmp_path: Path) -> None:
    service, project_id, episode_id = _legacy_database(tmp_path)

    assert _cancel(tmp_path, project_id, episode_id, "--run", "r2") == 0

    states = _states(service, project_id, episode_id)
    assert states["r2"][0] == "cancelled"
    assert states["r1"] == ("running", True)


def test_cli_cancel_rejects_a_run_of_another_episode(tmp_path: Path) -> None:
    service, project_id, episode_id = _legacy_database(tmp_path)
    assert _cancel(tmp_path, project_id, episode_id, "--run", "missing") == 2
    assert _states(service, project_id, episode_id)["r1"] == ("running", True)


def test_cli_cancel_never_executes_a_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, project_id, episode_id = _legacy_database(tmp_path)
    executed: list[str] = []
    from deeper_dive import pipeline as pipeline_module

    original = pipeline_module.PipelineOrchestrator.__init__

    def counting_init(self, repository, handlers, **kwargs):  # type: ignore[no-untyped-def]
        wrapped = {name: (lambda context, name=name: executed.append(name)) for name in handlers}
        original(self, repository, wrapped, **kwargs)

    monkeypatch.setattr(pipeline_module.PipelineOrchestrator, "__init__", counting_init)

    assert _cancel(tmp_path, project_id, episode_id) == 0

    assert executed == []
    assert _states(service, project_id, episode_id)["r1"][0] == "cancelled"
