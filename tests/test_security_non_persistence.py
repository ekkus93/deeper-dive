from __future__ import annotations

SENSITIVE_VALUE = "credential" + "-value"


def _diagnostics_module():
    return __import__(
        "deeper_dive.diagnostics",
        fromlist=["DiagnosticEvent", "StructuredDiagnosticLog"],
    )


def _export_module():
    return __import__("deeper_dive.export", fromlist=["EpisodeExporter"])


def _json_module():
    return __import__("json")


def _run_repository_module():
    return __import__(
        "deeper_dive.storage.run_repositories",
        fromlist=["GenerationRunRecord", "GenerationRunRepository"],
    )


def _database_module():
    return __import__("deeper_dive.storage.database", fromlist=["Database"])


def _user_config_module():
    return __import__(
        "deeper_dive.user_config",
        fromlist=["ProviderConfig", "UserConfig", "UserConfigStore"],
    )


def test_provider_config_persists_credential_reference_not_value(tmp_path) -> None:
    config = _user_config_module()
    path = tmp_path / "config.json"
    store = config.UserConfigStore(path)

    store.save(
        config.UserConfig(
            providers={
                "openai": config.ProviderConfig(
                    provider_type="openai",
                    credential_env="OPENAI_API_KEY",
                    default_model="gpt-test",
                )
            }
        )
    )
    text = path.read_text(encoding="utf-8")

    assert "OPENAI_API_KEY" in text
    assert SENSITIVE_VALUE not in text


def test_structured_diagnostics_store_no_credential_values(tmp_path) -> None:
    diagnostics = _diagnostics_module()
    log_path = tmp_path / "diagnostics.jsonl"
    log = diagnostics.StructuredDiagnosticLog(log_path)

    log.emit(
        diagnostics.DiagnosticEvent(
            level="error",
            event="provider_error",
            provider="fake",
            message="authorization: " + SENSITIVE_VALUE,
            details={"client_secret": SENSITIVE_VALUE},
        )
    )
    text = log_path.read_text(encoding="utf-8")

    assert SENSITIVE_VALUE not in text
    assert "[REDACTED]" in text


def test_generation_run_failure_persists_no_credential_values(tmp_path) -> None:
    database_module = _database_module()
    run_module = _run_repository_module()
    repository = run_module.GenerationRunRepository(database_module.Database(tmp_path / "p.db"))
    run = run_module.GenerationRunRecord(
        id="run-1",
        episode_id="episode-1",
        stage="conversation",
        state="failed",
        failure_code="stage_failed",
        failure_message="service_token=" + SENSITIVE_VALUE,
        created_at="now",
        modified_at="now",
    )

    repository.create(run)
    loaded = repository.get("run-1")

    assert loaded is not None
    assert loaded.failure_message == "service_token=[REDACTED]"
    assert SENSITIVE_VALUE not in loaded.failure_message


def test_export_metadata_persists_no_credential_values(tmp_path) -> None:
    export = _export_module()
    json = _json_module()
    path = tmp_path / "metadata.json"

    export.EpisodeExporter.write_metadata(
        path,
        {
            "access_token": SENSITIVE_VALUE,
            "refresh_token": SENSITIVE_VALUE,
            "client_secret": SENSITIVE_VALUE,
            "status": "ok",
            "provenance": {"run_id": "run-1", "model": "fake-v1"},
        },
    )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    text = json.dumps(loaded, sort_keys=True)

    assert SENSITIVE_VALUE not in text
    assert "access_token" not in loaded
    assert "refresh_token" not in loaded
    assert "client_secret" not in loaded
    assert loaded["status"] == "ok"
    assert loaded["provenance"] == {"model": "fake-v1", "run_id": "run-1"}
