from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from deeper_dive.storage.database import Database, LATEST_SCHEMA_VERSION


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

    with pytest.raises(RuntimeError, match="abort"):
        with database.transaction() as connection:
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
        assert connection.execute("SELECT value FROM legacy_payload").fetchone()[0] == "preserved"
        assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == LATEST_SCHEMA_VERSION
