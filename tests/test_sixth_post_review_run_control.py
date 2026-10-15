"""6PR-01: control flags survive a stale stage write; cancel finalizes without a stage."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from test_fifth_post_review_stopping_run import _cancel, _run, _states
from test_generation_start import _episode

from deeper_dive.pipeline import PipelineOrchestrator
from deeper_dive.storage.run_repositories import GenerationRunRepository


def _repository(tmp_path: Path):  # type: ignore[no-untyped-def]
    service, project_id, episode_id = _episode(tmp_path)
    return service, project_id, episode_id, service.runs(project_id)


def _flags(repository: GenerationRunRepository, run_id: str) -> tuple[str, bool, bool]:
    stored = repository.get(run_id)
    assert stored is not None
    return stored.state, stored.pause_requested, stored.cancel_requested


def test_stale_stage_write_keeps_a_cancel_request(tmp_path: Path) -> None:
    _, _, episode_id, runs = _repository(tmp_path)
    runs.create(_run("r1", episode_id, "running", "2026-01-01T00:00:00Z"))
    stale = runs.get("r1")  # a worker read this before the request
    assert stale is not None
    runs.request_cancel("r1", "2026-01-01T00:00:01Z")

    runs.update(replace(stale, stage="research", modified_at="2026-01-01T00:00:02Z"))

    assert _flags(runs, "r1") == ("running", False, True)


def test_stale_stage_write_keeps_a_pause_request_and_resume_clears_it(tmp_path: Path) -> None:
    _, _, episode_id, runs = _repository(tmp_path)
    runs.create(_run("r1", episode_id, "running", "2026-01-01T00:00:00Z"))
    stale = runs.get("r1")
    assert stale is not None
    runs.request_pause("r1", "2026-01-01T00:00:01Z")

    runs.update(replace(stale, stage="research", modified_at="2026-01-01T00:00:02Z"))
    assert _flags(runs, "r1") == ("running", True, False)

    paused = replace(stale, state="paused", modified_at="2026-01-01T00:00:03Z")
    runs.update(paused)
    pipeline = PipelineOrchestrator(runs, {"sources": lambda c: None}, stages=("sources",))
    pipeline.resume("r1")
    assert _flags(runs, "r1") == ("pending", False, False)


def test_stage_write_cannot_revive_a_cancelled_run(tmp_path: Path) -> None:
    _, _, episode_id, runs = _repository(tmp_path)
    runs.create(_run("r1", episode_id, "running", "2026-01-01T00:00:00Z"))
    stale = runs.get("r1")
    assert stale is not None
    assert runs.cancel_now("r1", "2026-01-01T00:00:01Z") is not None

    applied = runs.update(replace(stale, stage="tts", modified_at="2026-01-01T00:00:02Z"))

    assert applied is False
    assert _flags(runs, "r1") == ("cancelled", False, True)


def test_cancel_now_leaves_other_states_alone(tmp_path: Path) -> None:
    _, _, episode_id, runs = _repository(tmp_path)
    runs.create(_run("r1", episode_id, "completed", "2026-01-01T00:00:00Z"))
    stored = runs.cancel_now("r1", "2026-01-01T00:00:01Z")
    assert stored is not None and stored.state == "completed"
    assert runs.cancel_now("missing", "2026-01-01T00:00:01Z") is None


def test_cli_cancel_survives_a_worker_write_in_the_race_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    runs = service.runs(project_id)
    runs.create(_run("r1", episode_id, "running", "2026-01-01T00:00:00Z"))
    executed: list[str] = []
    original_init = PipelineOrchestrator.__init__

    def recording_init(self, repository, handlers, **kwargs):  # type: ignore[no-untyped-def]
        wrapped = {name: (lambda context, name=name: executed.append(name)) for name in handlers}
        original_init(self, repository, wrapped, **kwargs)

    monkeypatch.setattr(PipelineOrchestrator, "__init__", recording_init)

    # A live worker holds a record read before the cancel and writes it back inside
    # the window between the CLI's request and its finalize (baseline: request_cancel
    # then pipeline.run; now: a single cancel_now write).
    stale = runs.get("r1")
    assert stale is not None

    def worker_write() -> None:
        runs.update(replace(stale, stage="research", modified_at="2026-01-01T00:00:09Z"))

    original_request = GenerationRunRepository.request_cancel

    def request_then_worker(self, run_id, modified_at):  # type: ignore[no-untyped-def]
        original_request(self, run_id, modified_at)
        worker_write()

    monkeypatch.setattr(GenerationRunRepository, "request_cancel", request_then_worker)
    original_cancel_now = getattr(GenerationRunRepository, "cancel_now", None)
    if original_cancel_now is not None:

        def worker_then_cancel(self, run_id, modified_at):  # type: ignore[no-untyped-def]
            worker_write()
            return original_cancel_now(self, run_id, modified_at)

        monkeypatch.setattr(GenerationRunRepository, "cancel_now", worker_then_cancel)

    assert _cancel(tmp_path, project_id, episode_id) == 0

    assert executed == []
    assert _states(service, project_id, episode_id)["r1"][0] == "cancelled"


def test_no_stage_runs_when_a_cancel_lands_after_the_boundary_check(tmp_path: Path) -> None:
    _, _, episode_id, runs = _repository(tmp_path)
    runs.create(_run("r1", episode_id, "pending", "2026-01-01T00:00:00Z"))
    executed: list[str] = []
    pipeline = PipelineOrchestrator(
        runs,
        {"a": lambda c: executed.append("a"), "b": lambda c: executed.append("b")},
        stages=("a", "b"),
    )
    original_update = runs.update

    def cancel_before_the_running_write(run, **kwargs):  # type: ignore[no-untyped-def]
        # Another process cancels between the control check and the stage-start write.
        if run.state == "running":
            runs.cancel_now("r1", "2026-01-01T00:00:05Z")
        return original_update(run, **kwargs)

    runs.update = cancel_before_the_running_write  # type: ignore[method-assign]
    result = pipeline.run("r1")

    assert executed == []
    assert result.run.state == "cancelled"
    assert _flags(runs, "r1")[0] == "cancelled"


def test_cancel_now_refuses_a_run_that_already_finished(tmp_path: Path) -> None:
    _, _, episode_id, runs = _repository(tmp_path)
    runs.create(_run("r1", episode_id, "completed", "2026-01-01T00:00:00Z"))
    pipeline = PipelineOrchestrator(runs, {"a": lambda c: None}, stages=("a",))
    with pytest.raises(ValueError, match="cannot cancel"):
        pipeline.cancel_now("r1")
