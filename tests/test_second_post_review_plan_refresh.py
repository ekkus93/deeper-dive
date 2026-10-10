"""Production plan refresh cannot erase a pending guided segment edit."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.widgets import Input

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlannerService, PlannedSegment
from deeper_dive.guided_app import GuidedDeeperDiveApp
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_workflow import WizardKind, WizardState
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


class _TwoSegments:
    def generate_plan(self, _request):
        return {
            "segments": [
                {
                    "title": title,
                    "purpose": "Review evidence",
                    "target_duration_seconds": 600,
                    "questions": [],
                    "evidence_ids": [],
                    "lead_host_ids": [],
                }
                for title in ("Opening", "Analysis")
            ]
        }


def test_plan_refresh_preserves_dirty_edit_and_rehydrates_clean_form(tmp_path: Path) -> None:
    asyncio.run(_verify_plan_refresh(tmp_path))


async def _verify_plan_refresh(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Plan refresh")
    database = Database(service.workspaces.project_root(project.id) / "project.db")
    episode = EpisodeConfigurationService(database).create(
        project.id, EpisodeConfiguration(title="Episode", focus="Question")
    )
    planner = EpisodePlannerService(database, _TwoSegments())
    plan = planner.build_plan(episode.id)

    app = GuidedDeeperDiveApp(service)
    async with app.run_test(size=(100, 35)) as pilot:
        app.action_navigate("new")
        await pilot.pause()
        wizard = app.screen
        assert isinstance(wizard, GuidedEpisodeWizard)
        wizard.context.project_id = project.id
        wizard.context.episode_id = episode.id
        wizard.context.state = WizardState(WizardKind.NEW_DEEP_DIVE, "plan")
        wizard._planning_service = lambda: planner
        wizard._plan = planner.load_plan(episode.id)
        wizard._render_plan()
        wizard._toggle()
        await pilot.pause()
        wizard._remember_current_form()

        title = wizard.query_one("#guided-plan-title", Input)
        assert title.value == "Opening"
        title.value = "Unsaved opening"
        assert wizard._current_form_dirty()
        wizard._refresh_plan()
        assert title.value == "Unsaved opening"
        assert wizard._plan is not None and wizard._plan.id == plan.id
        assert wizard._current_form_dirty()

        title.value = "Opening"
        assert not wizard._current_form_dirty()
        original = plan.segments[0]
        revised = PlannedSegment(
            title="Updated elsewhere",
            purpose=original.purpose,
            target_duration_seconds=original.target_duration_seconds,
            questions=original.questions,
            evidence_ids=original.evidence_ids,
            lead_host_ids=original.lead_host_ids,
        )
        updated = planner.edit_segment(episode.id, 0, revised)
        wizard._refresh_plan()
        assert title.value == "Updated elsewhere"
        assert wizard._plan is not None and wizard._plan.id == updated.id
        assert not wizard._current_form_dirty()
