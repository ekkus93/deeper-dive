"""Persistence operations for replaceable episode plans."""

from __future__ import annotations

from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodePlanRecord, SegmentPlanRecord


class EpisodePlanRepository:
    """Persist the current plan for an episode atomically."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def replace(self, plan: EpisodePlanRecord, segments: list[SegmentPlanRecord]) -> None:
        with self.database.transaction() as db:
            existing = db.execute(
                "SELECT id FROM episode_plans WHERE episode_id=?", (plan.episode_id,)
            ).fetchone()
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
