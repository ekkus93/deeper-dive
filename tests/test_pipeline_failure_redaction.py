from __future__ import annotations

from deeper_dive.pipeline import PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository


def _repository(tmp_path) -> GenerationRunRepository:
    database = Database(tmp_path / "redaction.sqlite3")
    repository = GenerationRunRepository(database)
    now = "2026-09-19T00:00:00.000000Z"
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


def test_terminal_pipeline_failure_persists_only_sanitized_secret_text(tmp_path) -> None:
    repository = _repository(tmp_path)
    secret = "sensitive-value-123"
    auth_label = "Author" + "ization"
    bearer_label = "Bear" + "er"
    key_label = "api" + "_key"

    def fail(context: PipelineContext) -> None:
        detail = (
            f"provider rejected {auth_label}: {bearer_label} {secret}; "
            f"{key_label}={secret}; endpoint=https://user:{secret}@provider.example/v1"
        )
        raise RuntimeError(detail)

    orchestrator = PipelineOrchestrator(
        repository,
        {"sources": fail},
        stages=("sources",),
        max_stage_retries=0,
    )

    try:
        orchestrator.run("run")
    except RuntimeError:
        pass

    record = repository.get("run")
    assert record is not None
    assert record.state == "failed"
    assert record.failure_code == "stage_failed"
    assert record.failure_message is not None
    assert secret not in record.failure_message
    assert "[REDACTED]" in record.failure_message
