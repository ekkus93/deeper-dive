"""Persistent controller boundary used by the Research TUI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from deeper_dive.research_candidates import CandidateEvaluator, CandidateOutcome
from deeper_dive.research_gaps import ResearchGap, ResearchGapStore
from deeper_dive.research_policy import ResearchPolicy, ResearchPolicyStore
from deeper_dive.storage.database import Database

AnalyzeCallback = Callable[[str, str], tuple[ResearchGap, ...]]
ResearchCallback = Callable[[str, tuple[str, ...]], tuple[CandidateOutcome, ...]]


class PersistentResearchController:
    """Persist policy/focus/status while delegating provider-dependent orchestration."""

    def __init__(
        self,
        database_for_project: Callable[[str], Path],
        *,
        analyze_callback: AnalyzeCallback | None = None,
        research_callback: ResearchCallback | None = None,
    ) -> None:
        self.database_for_project = database_for_project
        self.analyze_callback = analyze_callback
        self.research_callback = research_callback

    def _database(self, project_id: str) -> Database:
        return Database(self.database_for_project(project_id))

    def policy(self, project_id: str) -> ResearchPolicy:
        return ResearchPolicyStore(self._database(project_id)).project(project_id)

    def save_policy(self, project_id: str, policy: ResearchPolicy, focus: str) -> None:
        database = self._database(project_id)
        ResearchPolicyStore(database).set_project(project_id, policy)
        self._ensure_focus_schema(database)
        with database.transaction() as db:
            db.execute(
                """INSERT INTO research_focus(project_id,focus) VALUES(?,?)
                ON CONFLICT(project_id) DO UPDATE SET focus=excluded.focus""",
                (project_id, focus),
            )

    def focus(self, project_id: str) -> str:
        database = self._database(project_id)
        self._ensure_focus_schema(database)
        with database.connection() as db:
            row = db.execute(
                "SELECT focus FROM research_focus WHERE project_id=?", (project_id,)
            ).fetchone()
        return "" if row is None else str(row["focus"])

    def analyze(self, project_id: str, focus: str) -> tuple[ResearchGap, ...]:
        if self.analyze_callback is None:
            raise RuntimeError("research-gap LLM is not configured")
        return self.analyze_callback(project_id, focus)

    def gaps(self, project_id: str) -> tuple[ResearchGap, ...]:
        return ResearchGapStore(self._database(project_id)).list_project(project_id)

    def set_gap_status(self, project_id: str, gap_id: str, status: str) -> None:
        database = self._database(project_id)
        ResearchGapStore(database)
        with database.transaction() as db:
            cursor = db.execute(
                "UPDATE research_gaps SET status=? WHERE project_id=? AND id=?",
                (status, project_id, gap_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(gap_id)

    def research(self, project_id: str, gap_ids: tuple[str, ...]) -> tuple[CandidateOutcome, ...]:
        if self.research_callback is None:
            raise RuntimeError("research search/fetch providers are not configured")
        return self.research_callback(project_id, gap_ids)

    def outcomes(self, project_id: str) -> tuple[CandidateOutcome, ...]:
        return CandidateEvaluator(self._database(project_id)).list_project(project_id)

    @staticmethod
    def _ensure_focus_schema(database: Database) -> None:
        with database.transaction() as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS research_focus (
                    project_id TEXT PRIMARY KEY,
                    focus TEXT NOT NULL
                )"""
            )
