from __future__ import annotations

from dataclasses import replace

import pytest

from deeper_dive.pipeline import PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import (
    CompletedUnitRecord,
    GenerationRunRecord,
    GenerationRunRepository,
)

STAGES = ("sources", "conversation", "export")


def _orchestrator(tmp_path) -> tuple[GenerationRunRepository, PipelineOrchestrator]:
    database = Database(tmp_path / "controls.sqlite3")
    repository = GenerationRunRepository(database)
    now = "2026-09-23T00:00:00.000000Z"
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES (?,?,?,?)",
            ("project", "Project", now, now),
        )
        connection.execute(
            "INSERT INTO episodes(id,project_id,title,created_at,modified_at) VALUES (?,?,?,?,?)",
            ("episode", "project", "Episode", now, now),
        )
    repository.create(GenerationRunRecord("run", "episode", "sources", "pending", now, now))
    pipeline = PipelineOrchestrator(
        repository,
        {stage: lambda context: None for stage in STAGES},
        stages=STAGES,
    )
    return repository, pipeline


def test_completed_run_rejects_pause_cancel_and_resume(tmp_path) -> None:
    _, pipeline = _orchestrator(tmp_path)
    completed = pipeline.run("run")
    assert completed.run.state == "completed"

    with pytest.raises(ValueError, match="cannot pause.*completed"):
        pipeline.request_pause("run")
    with pytest.raises(ValueError, match="cannot cancel.*completed"):
        pipeline.request_cancel("run")
    with pytest.raises(ValueError, match="cannot resume.*completed"):
        pipeline.resume("run")


def test_pending_run_rejects_resume(tmp_path) -> None:
    _, pipeline = _orchestrator(tmp_path)

    with pytest.raises(ValueError, match="cannot resume.*pending"):
        pipeline.resume("run")


def test_paused_run_can_cancel_but_cancelled_run_cannot_resume(tmp_path) -> None:
    _, pipeline = _orchestrator(tmp_path)
    pipeline.request_pause("run")
    paused = pipeline.run("run")
    assert paused.run.state == "paused"

    pipeline.request_cancel("run")
    cancelled = pipeline.run("run")
    assert cancelled.run.state == "cancelled"

    with pytest.raises(ValueError, match="cancelled runs cannot be resumed"):
        pipeline.resume("run")


def test_paused_run_resumes_from_completed_checkpoint(tmp_path) -> None:
    repository, pipeline = _orchestrator(tmp_path)
    repository.complete_unit(
        CompletedUnitRecord("run", "sources", "stage", "2026-09-23T00:01:00.000000Z")
    )
    current = repository.get("run")
    assert current is not None
    repository.update(replace(current, state="paused", stage="sources", pause_requested=True))

    resumed = pipeline.resume("run")
    assert resumed.state == "pending"
    result = pipeline.run("run")

    assert result.run.state == "completed"
    assert result.skipped_stages == ("sources",)
    assert result.executed_stages == ("conversation", "export")
