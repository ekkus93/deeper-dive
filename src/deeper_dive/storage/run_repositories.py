"""Durable generation-run state and idempotent work-unit checkpoints."""

from __future__ import annotations

from dataclasses import dataclass, replace

from deeper_dive.diagnostics import redact
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_errors import (
    EpisodeConfigurationConflict,
    GenerationRunStillStopping,
)


@dataclass(frozen=True, slots=True)
class GenerationRunRecord:
    id: str
    episode_id: str
    stage: str
    state: str
    created_at: str
    modified_at: str
    retry_count: int = 0
    failure_code: str | None = None
    failure_message: str | None = None
    pause_requested: bool = False
    cancel_requested: bool = False


@dataclass(frozen=True, slots=True)
class CompletedUnitRecord:
    run_id: str
    stage: str
    unit_id: str
    completed_at: str


class GenerationRunRepository:
    """Persistence boundary for resumable generation execution."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def create(self, run: GenerationRunRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO generation_runs(
                    id,episode_id,stage,state,retry_count,failure_code,failure_message,
                    pause_requested,cancel_requested,created_at,modified_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                self._values(run),
            )

    def select_or_create(
        self,
        run: GenerationRunRecord,
        *,
        active_states: frozenset[str],
        terminal_states: frozenset[str],
        expected_episode_config_json: str | None = None,
    ) -> tuple[GenerationRunRecord, bool]:
        """Atomically return the active run or insert ``run`` (``created`` is True).

        Runs under ``BEGIN IMMEDIATE`` so two concurrent starts serialize: the
        second sees the first's pending run instead of inserting another. When
        ``expected_episode_config_json`` is given, the episode revision seen at
        preflight is rechecked inside the same transaction.
        """

        with self.database.transaction(immediate=True) as db:
            if expected_episode_config_json is not None:
                episode = db.execute(
                    "SELECT config_json FROM episodes WHERE id=?", (run.episode_id,)
                ).fetchone()
                if episode is None:
                    raise KeyError(run.episode_id)
                if episode["config_json"] != expected_episode_config_json:
                    raise EpisodeConfigurationConflict(
                        "episode configuration changed after preflight; "
                        "review the episode and start again"
                    )
            rows = db.execute(
                """SELECT * FROM generation_runs WHERE episode_id=?
                ORDER BY modified_at DESC,id DESC""",
                (run.episode_id,),
            ).fetchall()
            records = [self._from_row(dict(row)) for row in rows]
            active = [item for item in records if item.state in active_states]
            # Cancellation is honored only at a stage boundary, so a pending or
            # running run with a cancel request keeps executing; a second run would
            # share its episode-keyed state. A paused run executes nothing and can
            # never reach a boundary, so its cancel request does not block a new run.
            stopping = [item for item in active if item.cancel_requested and item.state != "paused"]
            if stopping:
                oldest = min(stopping, key=lambda item: (item.created_at, item.id))
                raise GenerationRunStillStopping(
                    f"the previous run {oldest.id} is still stopping; wait for it to finish, "
                    "or if its worker is gone run `deeper-dive episode cancel "
                    f"<project_id> {run.episode_id} --run {oldest.id}` to finish stopping it, "
                    "then start again"
                )
            reusable = [item for item in active if not item.cancel_requested]
            if reusable:
                return reusable[0], False
            latest = records[0] if records else None
            if latest is not None and latest.state not in terminal_states | active_states:
                raise ValueError(
                    f"cannot start generation from unsupported run state: {latest.state}"
                )
            db.execute(
                """INSERT INTO generation_runs(
                    id,episode_id,stage,state,retry_count,failure_code,failure_message,
                    pause_requested,cancel_requested,created_at,modified_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                self._values(run),
            )
        return run, True

    def get(self, run_id: str) -> GenerationRunRecord | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM generation_runs WHERE id=?", (run_id,)).fetchone()
        return None if row is None else self._from_row(dict(row))

    def blocking_cancel_run(self, episode_id: str) -> GenerationRunRecord | None:
        """Oldest pending/running run with a cancel request: the run that blocks a new start."""

        with self.database.connection() as db:
            row = db.execute(
                """SELECT * FROM generation_runs
                WHERE episode_id=? AND state IN ('pending','running') AND cancel_requested=1
                ORDER BY created_at ASC,id ASC LIMIT 1""",
                (episode_id,),
            ).fetchone()
        return self._from_row(dict(row)) if row is not None else None

    def latest_for_episode(self, episode_id: str) -> GenerationRunRecord | None:
        with self.database.connection() as db:
            row = db.execute(
                """SELECT * FROM generation_runs WHERE episode_id=?
                ORDER BY modified_at DESC,id DESC LIMIT 1""",
                (episode_id,),
            ).fetchone()
        return None if row is None else self._from_row(dict(row))

    def update(self, run: GenerationRunRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                """UPDATE generation_runs SET
                    stage=?,state=?,retry_count=?,failure_code=?,failure_message=?,
                    pause_requested=?,cancel_requested=?,modified_at=? WHERE id=?""",
                (
                    run.stage,
                    run.state,
                    run.retry_count,
                    run.failure_code,
                    self._safe_failure_message(run.failure_message),
                    int(run.pause_requested),
                    int(run.cancel_requested),
                    run.modified_at,
                    run.id,
                ),
            )

    def request_pause(self, run_id: str, modified_at: str) -> None:
        self._set_flag(run_id, "pause_requested", modified_at)

    def request_cancel(self, run_id: str, modified_at: str) -> None:
        self._set_flag(run_id, "cancel_requested", modified_at)

    def complete_unit(self, unit: CompletedUnitRecord) -> bool:
        """Commit one work-unit checkpoint; return False when already complete."""
        with self.database.transaction() as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO generation_run_units(run_id,stage,unit_id,completed_at)
                VALUES (?,?,?,?)""",
                (unit.run_id, unit.stage, unit.unit_id, unit.completed_at),
            )
            return cursor.rowcount == 1

    def list_completed_units(self, run_id: str, stage: str) -> list[CompletedUnitRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT run_id,stage,unit_id,completed_at FROM generation_run_units
                WHERE run_id=? AND stage=? ORDER BY unit_id""",
                (run_id, stage),
            ).fetchall()
        return [CompletedUnitRecord(**dict(row)) for row in rows]

    def list_completed_units_all(self, run_id: str) -> list[CompletedUnitRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                """SELECT run_id,stage,unit_id,completed_at FROM generation_run_units
                WHERE run_id=? ORDER BY completed_at,stage,unit_id""",
                (run_id,),
            ).fetchall()
        return [CompletedUnitRecord(**dict(row)) for row in rows]

    def list_completed_stages(self, run_id: str) -> list[str]:
        return [
            unit.stage for unit in self.list_completed_units_all(run_id) if unit.unit_id == "stage"
        ]

    def _set_flag(self, run_id: str, column: str, modified_at: str) -> None:
        if column not in {"pause_requested", "cancel_requested"}:
            raise ValueError("unsupported run flag")
        with self.database.transaction() as db:
            db.execute(
                f"UPDATE generation_runs SET {column}=1,modified_at=? WHERE id=?",
                (modified_at, run_id),
            )

    @staticmethod
    def _safe_failure_message(message: str | None) -> str | None:
        if message is None:
            return None
        return str(redact(message))

    @classmethod
    def _values(cls, run: GenerationRunRecord) -> tuple[object, ...]:
        return (
            run.id,
            run.episode_id,
            run.stage,
            run.state,
            run.retry_count,
            run.failure_code,
            cls._safe_failure_message(run.failure_message),
            int(run.pause_requested),
            int(run.cancel_requested),
            run.created_at,
            run.modified_at,
        )

    @staticmethod
    def _from_row(data: dict[str, object]) -> GenerationRunRecord:
        data["pause_requested"] = bool(data["pause_requested"])
        data["cancel_requested"] = bool(data["cancel_requested"])
        return GenerationRunRecord(**data)  # type: ignore[arg-type]

    @staticmethod
    def with_failure(
        run: GenerationRunRecord,
        *,
        code: str,
        sanitized_message: str,
        modified_at: str,
    ) -> GenerationRunRecord:
        return replace(
            run,
            state="failed",
            retry_count=run.retry_count + 1,
            failure_code=code,
            failure_message=sanitized_message,
            modified_at=modified_at,
        )
