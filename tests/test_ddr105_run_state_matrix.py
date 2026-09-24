from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository

STAGES = ("sources", "conversation", "tts", "export")
NOW = "2026-09-23T00:00:00.000000Z"


def _repository(tmp_path: Path) -> GenerationRunRepository:
    database = Database(tmp_path / "run-state.sqlite3")
    repository = GenerationRunRepository(database)
    with database.transaction() as db:
        db.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES (?,?,?,?)",
            ("project", "Project", NOW, NOW),
        )
        db.execute(
            "INSERT INTO episodes(id,project_id,title,created_at,modified_at) VALUES (?,?,?,?,?)",
            ("episode", "project", "Episode", NOW, NOW),
        )
    repository.create(GenerationRunRecord("run", "episode", "sources", "pending", NOW, NOW))
    return repository


def test_pending_enters_running_and_reaches_completed(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    observed: list[str] = []

    def handler(context: PipelineContext) -> None:
        record = repository.get(context.run_id)
        assert record is not None
        observed.append(record.state)

    result = PipelineOrchestrator(
        repository, {stage: handler for stage in STAGES}, stages=STAGES
    ).run("run")

    assert observed == ["running"] * len(STAGES)
    assert result.run.state == "completed"


def test_running_failure_is_durable_and_terminal(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    def fail(context: PipelineContext) -> None:
        record = repository.get(context.run_id)
        assert record is not None
        assert record.state == "running"
        raise RuntimeError("deterministic failure")

    orchestrator = PipelineOrchestrator(
        repository,
        {stage: (fail if stage == "sources" else lambda context: None) for stage in STAGES},
        stages=STAGES,
        max_stage_retries=0,
    )

    with pytest.raises(RuntimeError, match="deterministic failure"):
        orchestrator.run("run")

    failed = repository.get("run")
    assert failed is not None
    assert failed.state == "failed"
    with pytest.raises(ValueError, match="failed"):
        orchestrator.resume("run")


def test_pause_resume_restart_and_cancel_matrix(tmp_path: Path) -> None:
    repository = _repository(tmp_path)

    def pause_after_conversation(context: PipelineContext) -> None:
        if context.stage == "conversation":
            repository.request_pause(context.run_id, NOW)

    first = PipelineOrchestrator(
        repository,
        {stage: pause_after_conversation for stage in STAGES},
        stages=STAGES,
    ).run("run")
    assert first.run.state == "paused"
    assert first.executed_stages == ("sources", "conversation")

    restarted = PipelineOrchestrator(
        repository, {stage: lambda context: None for stage in STAGES}, stages=STAGES
    )
    restarted.resume("run")
    resumed = restarted.run("run")
    assert resumed.run.state == "completed"
    assert resumed.skipped_stages == ("sources", "conversation")

    # A terminal completed run rejects control transitions rather than silently mutating state.
    with pytest.raises(ValueError, match="completed"):
        restarted.resume("run")
