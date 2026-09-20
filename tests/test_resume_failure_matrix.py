from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.pipeline import DEFAULT_STAGES, PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository


@pytest.mark.parametrize("failed_stage", DEFAULT_STAGES)
def test_restart_after_failure_at_every_pipeline_stage(tmp_path: Path, failed_stage: str) -> None:
    database = Database(tmp_path / f"{failed_stage}.db")
    repository = GenerationRunRepository(database)
    now = "2026-09-20T00:00:00.000000Z"
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
    failed_once = False

    def flaky(context: PipelineContext) -> None:
        nonlocal failed_once
        if context.stage == failed_stage and not failed_once:
            failed_once = True
            raise RuntimeError(f"fixture failure: {failed_stage}")

    first = PipelineOrchestrator(
        repository,
        {stage: flaky for stage in DEFAULT_STAGES},
        max_stage_retries=0,
    )
    with pytest.raises(RuntimeError, match="fixture failure"):
        first.run("run")
    record = repository.get("run")
    assert record is not None
    assert record.state == "failed"
    assert not repository.list_completed_units("run", failed_stage)

    calls: list[str] = []

    def healthy(context: PipelineContext) -> None:
        calls.append(context.stage)

    restarted = PipelineOrchestrator(
        GenerationRunRepository(Database(database.path)),
        {stage: healthy for stage in DEFAULT_STAGES},
        max_stage_retries=0,
    )
    result = restarted.run("run")
    failed_index = DEFAULT_STAGES.index(failed_stage)
    assert result.run.state == "completed"
    assert result.skipped_stages == DEFAULT_STAGES[:failed_index]
    assert calls == list(DEFAULT_STAGES[failed_index:])
