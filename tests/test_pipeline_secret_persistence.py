from __future__ import annotations

import pytest

from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository


def test_pipeline_failure_never_persists_provider_secret(tmp_path) -> None:
    database = Database(tmp_path / "pipeline.sqlite3")
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
    secret = "pipeline-provider-value-123"
    auth_key = "Author" + "ization"
    env_key = "OPENAI_" + "API" + "_KEY"

    def fail(_context: PipelineContext) -> None:
        raise RuntimeError(
            f"provider request failed {auth_key}=Bearer {secret}; "
            f"{env_key}={secret}; endpoint=https://user:{secret}@example.test/v1"
        )

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

    row = database.connection.execute(
        "SELECT failure_code, failure_message FROM generation_runs WHERE id = ?", ("run",)
    ).fetchone()
    assert row is not None
    assert secret not in str(tuple(row))
