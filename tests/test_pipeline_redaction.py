from __future__ import annotations

import pytest

from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository


def _repository(tmp_path) -> GenerationRunRepository:
    database = Database(tmp_path / "pipeline-redaction.sqlite3")
    repository = GenerationRunRepository(database)
    now = "2026-09-21T00:00:00.000000Z"
    with database.transaction() as db:
        db.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES (?,?,?,?)",
            ("project", "Project", now, now),
        )
        db.execute(
            "INSERT INTO episodes(id,project_id,title,created_at,modified_at) VALUES (?,?,?,?,?)",
            ("episode", "project", "Episode", now, now),
        )
    repository.create(GenerationRunRecord("run", "episode", "sources", "pending", now, now))
    return repository


def test_terminal_pipeline_failure_persists_only_sanitized_exception_text(tmp_path) -> None:
    repository = _repository(tmp_path)
    secret = "runtime" + "-credential-981"
    key_name = "api" + "_" + "key"

    def fail(context: PipelineContext) -> None:
        raise RuntimeError(f"provider rejected {key_name}={secret} for {context.stage}")

    orchestrator = PipelineOrchestrator(
        repository,
        {"sources": fail},
        stages=("sources",),
        max_stage_retries=0,
    )

    with pytest.raises(RuntimeError):
        orchestrator.run("run")

    record = repository.get("run")
    assert record is not None
    assert record.state == "failed"
    assert record.failure_code == "stage_failed"
    assert record.failure_message is not None
    assert secret not in record.failure_message
    assert "[REDACTED]" in record.failure_message
    assert "provider rejected" in record.failure_message
