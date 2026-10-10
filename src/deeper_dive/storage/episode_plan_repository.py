"""Persistence operations for replaceable episode plans."""

from __future__ import annotations

import sqlite3

from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodePlanRecord, SegmentPlanRecord


class EpisodePlanRepository:
    """Persist the current plan for an episode atomically."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def require_editable(self, episode_id: str) -> None:
        with self.database.connection() as db:
            existing = db.execute(
                "SELECT id FROM episode_plans WHERE episode_id=?", (episode_id,)
            ).fetchone()
            if (existing is not None and self._started(db, episode_id)) or self._started(
                db, episode_id, include_runs=False
            ):
                raise ValueError("plan is frozen after generation starts; create a new episode")

    def require_configuration_editable(self, episode_id: str) -> None:
        """Freeze semantic episode configuration once any generation work exists.

        Planner resume has a narrower exception that permits creation of an initial
        plan after a run record exists. Episode configuration does not: changing
        hosts, focus, duration, research/model/source overrides, or other snapshot
        fields after a run exists would mutate the inputs bound to historical work.
        """
        with self.database.connection() as db:
            if self._started(db, episode_id):
                raise ValueError(
                    "episode configuration is frozen after generation starts; create a new episode"
                )

    @staticmethod
    def _started(db: sqlite3.Connection, episode_id: str, *, include_runs: bool = True) -> bool:
        tables = ("generation_runs",) if include_runs else ()
        for table in (*tables, "conversation_states", "conversation_turns"):
            if (
                db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                ).fetchone()
                and db.execute(
                    f"SELECT 1 FROM {table} WHERE episode_id=? LIMIT 1", (episode_id,)
                ).fetchone()
            ):
                return True
        return False

    def replace(self, plan: EpisodePlanRecord, segments: list[SegmentPlanRecord]) -> None:
        with self.database.transaction() as db:
            existing = db.execute(
                "SELECT id FROM episode_plans WHERE episode_id=?", (plan.episode_id,)
            ).fetchone()
            if existing is None and self._started(db, plan.episode_id, include_runs=False):
                raise ValueError("plan is frozen after generation starts; create a new episode")
            if existing is not None and self._started(db, plan.episode_id):
                current = db.execute(
                    "SELECT plan_json FROM episode_plans WHERE id=?", (existing["id"],)
                ).fetchone()
                persisted = db.execute(
                    "SELECT ordinal,title,purpose,target_duration_seconds,segment_json "
                    "FROM segment_plans WHERE episode_plan_id=? ORDER BY ordinal",
                    (existing["id"],),
                ).fetchall()
                expected = [
                    (
                        item.ordinal,
                        item.title,
                        item.purpose,
                        item.target_duration_seconds,
                        item.segment_json,
                    )
                    for item in segments
                ]
                if (
                    existing["id"] != plan.id
                    or current["plan_json"] != plan.plan_json
                    or [tuple(row) for row in persisted] != expected
                ):
                    raise ValueError("plan is frozen after generation starts; create a new episode")
                # Approval changes metadata only. Preserve segment identities and history.
                db.execute(
                    "UPDATE episode_plans SET status=?,modified_at=? WHERE id=?",
                    (plan.status, plan.modified_at, plan.id),
                )
                return
            if existing is not None:
                db.execute("DELETE FROM episode_plans WHERE id=?", (existing["id"],))
            db.execute(
                """INSERT INTO episode_plans(id,episode_id,status,plan_json,created_at,modified_at)
                VALUES (?,?,?,?,?,?)""",
                (
                    plan.id,
                    plan.episode_id,
                    plan.status,
                    plan.plan_json,
                    plan.created_at,
                    plan.modified_at,
                ),
            )
            for segment in segments:
                db.execute(
                    """INSERT INTO segment_plans(
                    id,episode_plan_id,ordinal,title,purpose,target_duration_seconds,segment_json
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (
                        segment.id,
                        segment.episode_plan_id,
                        segment.ordinal,
                        segment.title,
                        segment.purpose,
                        segment.target_duration_seconds,
                        segment.segment_json,
                    ),
                )
