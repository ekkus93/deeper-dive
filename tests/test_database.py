from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from deeper_dive.storage.database import LATEST_SCHEMA_VERSION, Database


def test_fresh_database_initializes_and_reopens_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "project.db"
    database = Database(path)

    assert database.initialize() == LATEST_SCHEMA_VERSION
    assert path.is_file()
    assert database.initialize() == LATEST_SCHEMA_VERSION

    with database.connection() as connection:
        row = connection.execute("SELECT version FROM schema_version").fetchone()
        assert row is not None
        assert row["version"] == LATEST_SCHEMA_VERSION


def test_connection_enables_foreign_keys_wal_and_busy_timeout(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db", busy_timeout_ms=4321)
    database.initialize()

    with database.connection() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 4321


def test_transaction_commits_success_and_rolls_back_failure(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()

    with database.transaction() as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table(value) VALUES ('kept')")

    with pytest.raises(RuntimeError, match="abort"), database.transaction() as connection:
        connection.execute("INSERT INTO values_table(value) VALUES ('rolled-back')")
        raise RuntimeError("abort")

    with database.connection() as connection:
        values = [row[0] for row in connection.execute("SELECT value FROM values_table")]
    assert values == ["kept"]


def test_older_fixture_database_migrates_safely(tmp_path: Path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE legacy_payload (value TEXT NOT NULL)")
        connection.execute("INSERT INTO legacy_payload(value) VALUES ('preserved')")
        connection.commit()

    database = Database(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION

    with database.connection() as connection:
        legacy_row = connection.execute("SELECT value FROM legacy_payload").fetchone()
        version_row = connection.execute("SELECT version FROM schema_version").fetchone()
        assert legacy_row is not None
        assert version_row is not None
        assert legacy_row[0] == "preserved"
        assert version_row[0] == LATEST_SCHEMA_VERSION


def test_v7_tts_artifact_schema_migrates_to_per_turn_cache_rows(tmp_path: Path) -> None:
    path = tmp_path / "v7.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE schema_version (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_version(version) VALUES (7)")
        connection.execute(
            """CREATE TABLE tts_artifacts (
                turn_id TEXT PRIMARY KEY,
                artifact_id TEXT NOT NULL,
                cache_key TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL,
                path TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                voice TEXT NOT NULL,
                model TEXT
            )"""
        )
        connection.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model
            ) VALUES (?,?,?,?,?,?,?,?)""",
            ("t1", "a1", "shared", "complete", "/tmp/a.wav", "p", "v", "m"),
        )
        connection.commit()

    database = Database(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION

    with database.transaction() as connection:
        columns = {
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(tts_artifacts)").fetchall()
        }
        assert "format" in columns
        connection.execute(
            """INSERT INTO tts_artifacts(
                turn_id,artifact_id,cache_key,status,path,provider_id,voice,model,format
            ) VALUES (?,?,?,?,?,?,?,?,?)""",
            ("t2", "a1", "shared", "complete", "/tmp/a.wav", "p", "v", "m", "wav"),
        )
        rows = connection.execute(
            "SELECT turn_id,cache_key FROM tts_artifacts ORDER BY turn_id"
        ).fetchall()
    assert [(str(row["turn_id"]), str(row["cache_key"])) for row in rows] == [
        ("t1", "shared"),
        ("t2", "shared"),
    ]
