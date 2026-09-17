"""SQLite connection, transaction, and migration foundation."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.domain.errors import StorageError

LATEST_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered SQLite schema migration."""

    version: int
    statements: tuple[str, ...]


_MIGRATIONS = (
    Migration(
        version=1,
        statements=(
            """
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER NOT NULL
            )
            """,
        ),
    ),
)


class Database:
    """Own a SQLite database path and provide safe connection boundaries."""

    def __init__(self, path: Path | str, *, busy_timeout_ms: int = 5000) -> None:
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be non-negative")
        self.path = Path(path)
        self.busy_timeout_ms = busy_timeout_ms

    def connect(self) -> sqlite3.Connection:
        """Open one configured connection with foreign keys enabled."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and always close it."""

        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit successful work and roll back any exception."""

        with self.connection() as connection:
            try:
                connection.execute("BEGIN")
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def initialize(self) -> int:
        """Initialize or migrate the database to the latest schema."""

        with self.transaction() as connection:
            current = self._current_version(connection)
            if current > LATEST_SCHEMA_VERSION:
                raise StorageError(
                    f"database schema {current} is newer than supported "
                    f"schema {LATEST_SCHEMA_VERSION}"
                )
            for migration in _MIGRATIONS:
                if migration.version <= current:
                    continue
                for statement in migration.statements:
                    connection.execute(statement)
                self._set_version(connection, migration.version)
                current = migration.version
            return current

    @staticmethod
    def _current_version(connection: sqlite3.Connection) -> int:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_version'"
        ).fetchone()
        if exists is None:
            return 0
        rows = connection.execute("SELECT version FROM schema_version").fetchall()
        if not rows:
            return 0
        if len(rows) != 1:
            raise StorageError("schema_version must contain exactly one row")
        return int(rows[0]["version"])

    @staticmethod
    def _set_version(connection: sqlite3.Connection, version: int) -> None:
        connection.execute("DELETE FROM schema_version")
        connection.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
