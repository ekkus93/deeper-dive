"""SQLite connection, transaction, and migration foundation."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.domain.errors import StorageError

LATEST_SCHEMA_VERSION = 4


@dataclass(frozen=True, slots=True)
class Migration:
    """One ordered SQLite schema migration."""

    version: int
    statements: tuple[str, ...]


_MIGRATIONS = (
    Migration(
        version=1,
        statements=("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)",),
    ),
    Migration(
        version=2,
        statements=(
            """CREATE TABLE projects (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL, instructions TEXT NOT NULL DEFAULT ''
            )""",
            """CREATE TABLE sources (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                origin TEXT NOT NULL CHECK(origin IN ('user','supplemental','generated_reference')),
                source_type TEXT NOT NULL, title TEXT NOT NULL, locator TEXT,
                content_hash TEXT, included INTEGER NOT NULL DEFAULT 1 CHECK(included IN (0,1)),
                status TEXT NOT NULL DEFAULT 'pending', imported_at TEXT NOT NULL
            )""",
            """CREATE TABLE source_chunks (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, text TEXT NOT NULL, content_hash TEXT NOT NULL,
                location TEXT, UNIQUE(source_id, ordinal)
            )""",
            "CREATE INDEX source_project_idx ON sources(project_id)",
            "CREATE INDEX chunk_source_idx ON source_chunks(source_id)",
        ),
    ),
    Migration(
        version=3,
        statements=(
            """CREATE TABLE hosts (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                display_name TEXT NOT NULL,
                preset_origin TEXT,
                role TEXT NOT NULL DEFAULT '',
                expertise TEXT NOT NULL DEFAULT '',
                instructions TEXT NOT NULL DEFAULT '',
                behavior_json TEXT NOT NULL DEFAULT '{}',
                evidence_priorities_json TEXT NOT NULL DEFAULT '[]',
                tts_provider TEXT,
                tts_voice TEXT
            )""",
            """CREATE TABLE host_relationships (
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                from_host_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
                to_host_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE CASCADE,
                relationship_json TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY(from_host_id, to_host_id),
                CHECK(from_host_id <> to_host_id)
            )""",
            """CREATE TABLE episodes (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                focus TEXT NOT NULL DEFAULT '',
                audience TEXT NOT NULL DEFAULT '',
                technical_depth TEXT NOT NULL DEFAULT '',
                target_duration_seconds INTEGER NOT NULL DEFAULT 0,
                style TEXT NOT NULL DEFAULT '',
                state TEXT NOT NULL DEFAULT 'draft',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )""",
            """CREATE TABLE episode_hosts (
                episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                host_id TEXT NOT NULL REFERENCES hosts(id) ON DELETE RESTRICT,
                ordinal INTEGER NOT NULL,
                PRIMARY KEY(episode_id, host_id),
                UNIQUE(episode_id, ordinal)
            )""",
            """CREATE TABLE episode_plans (
                id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL UNIQUE REFERENCES episodes(id) ON DELETE CASCADE,
                status TEXT NOT NULL DEFAULT 'draft',
                plan_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )""",
            """CREATE TABLE segment_plans (
                id TEXT PRIMARY KEY,
                episode_plan_id TEXT NOT NULL REFERENCES episode_plans(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL,
                title TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT '',
                target_duration_seconds INTEGER NOT NULL DEFAULT 0,
                segment_json TEXT NOT NULL DEFAULT '{}',
                UNIQUE(episode_plan_id, ordinal)
            )""",
            "CREATE INDEX host_project_idx ON hosts(project_id)",
            "CREATE INDEX episode_project_idx ON episodes(project_id)",
            "CREATE INDEX episode_host_host_idx ON episode_hosts(host_id)",
            "CREATE INDEX segment_plan_parent_idx ON segment_plans(episode_plan_id)",
        ),
    ),
    Migration(
        version=4,
        statements=(
            """CREATE TABLE generation_runs (
                id TEXT PRIMARY KEY,
                episode_id TEXT NOT NULL REFERENCES episodes(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                state TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0 CHECK(retry_count >= 0),
                failure_code TEXT,
                failure_message TEXT,
                pause_requested INTEGER NOT NULL DEFAULT 0 CHECK(pause_requested IN (0,1)),
                cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK(cancel_requested IN (0,1)),
                created_at TEXT NOT NULL,
                modified_at TEXT NOT NULL
            )""",
            """CREATE TABLE generation_run_units (
                run_id TEXT NOT NULL REFERENCES generation_runs(id) ON DELETE CASCADE,
                stage TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                PRIMARY KEY(run_id, stage, unit_id)
            )""",
            "CREATE INDEX generation_run_episode_idx ON generation_runs(episode_id)",
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=self.busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
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
        with self.transaction() as connection:
            current = self._current_version(connection)
            if current > LATEST_SCHEMA_VERSION:
                raise StorageError(
                    f"database schema {current} is newer than supported schema "
                    f"{LATEST_SCHEMA_VERSION}"
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
