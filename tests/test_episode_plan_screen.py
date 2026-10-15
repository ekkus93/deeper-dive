from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from textual.widgets import Checkbox, Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_plan_screen import EpisodePlanScreen
from deeper_dive.episode_planner import EpisodePlan, EpisodePlannerService, PlannedSegment
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp


class FakePlanController:
    def __init__(self) -> None:
        self.plan = EpisodePlan(
            "plan-1",
            "episode-1",
            (
                PlannedSegment(
                    "Opening",
                    "Frame the question",
                    300,
                    ("Why?",),
                    ("chunk-1",),
                    ("host-1",),
                ),
                PlannedSegment(
                    "Evidence", "Test the claim", 600, ("What evidence?",), (), ("host-2",)
                ),
            ),
        )
        self.regenerated_segment: int | None = None
        self.regenerated_plan = False
        self.approved = False

    def load_plan(self, episode_id: str) -> EpisodePlan:
        assert episode_id == "episode-1"
        return self.plan

    def regenerate_plan(self, episode_id: str) -> EpisodePlan:
        self.regenerated_plan = True
        self.plan = replace(self.plan, segments=(replace(self.plan.segments[0], title="New plan"),))
        return self.plan

    def regenerate_segment(self, episode_id: str, ordinal: int) -> EpisodePlan:
        self.regenerated_segment = ordinal
        segments = list(self.plan.segments)
        segments[ordinal] = replace(segments[ordinal], title="Regenerated")
        self.plan = replace(self.plan, segments=tuple(segments))
        return self.plan

    def edit_segment(self, episode_id: str, ordinal: int, segment: PlannedSegment) -> EpisodePlan:
        segments = list(self.plan.segments)
        segments[ordinal] = segment
        self.plan = replace(self.plan, segments=tuple(segments))
        return self.plan

    def approve_plan(self, episode_id: str, reviewed_plan_id: str | None = None) -> EpisodePlan:
        self.approved = True
        return self.plan


def test_plan_screen_renders_edits_regenerates_and_requires_approval(tmp_path: Path) -> None:
    asyncio.run(_exercise_plan_review(tmp_path))


async def _exercise_plan_review(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    controller = FakePlanController()
    app = DeeperDiveApp(service, episode_plan_controller=controller)
    async with app.run_test(size=(120, 50)) as pilot:
        app.current_episode_id = "episode-1"
        app.action_navigate("plan")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodePlanScreen)
        listing = str(screen.query_one("#segment-list", Static).content)
        assert "Opening" in listing
        assert "900s" in listing
        assert "chunk-1" in listing
        assert not app.plan_approved

        screen.query_one("#segment-number", Input).value = "2"
        screen.action_select_segment()
        screen.query_one("#segment-title", Input).value = "Edited evidence"
        screen.query_one("#segment-purpose", Input).value = "Challenge the evidence"
        screen.query_one("#segment-duration", Input).value = "650"
        screen.action_save_segment()
        assert controller.plan.segments[1].title == "Edited evidence"

        screen.action_regenerate_segment()
        assert controller.regenerated_segment == 1
        assert controller.plan.segments[1].title == "Regenerated"

        screen.action_regenerate_plan()
        assert controller.regenerated_plan
        assert not app.plan_approved

        screen.action_approve_generate()
        assert controller.approved
        assert app.plan_approved
        assert not app.auto_generate_after_approval


def test_plan_screen_explicit_auto_generate_routes_to_generation(tmp_path: Path) -> None:
    asyncio.run(_exercise_auto_generate(tmp_path))


def test_empty_stored_plan_actions_show_regenerate_instruction(tmp_path: Path) -> None:
    async def run() -> None:
        service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
        project = service.create_project("Empty plan")
        database = Database(service.workspaces.project_root(project.id) / "project.db")
        hosts = HostEpisodeRepository(database)
        hosts.create_host(
            create_host_from_preset("skeptic", project.id, host_id="host").to_record()
        )
        episode = EpisodeConfigurationService(database).create(
            project.id, EpisodeConfiguration(title="Empty", host_ids=("host",))
        )

        class Generator:
            def generate_plan(self, request: dict[str, object]) -> dict[str, object]:
                _ = request
                return {
                    "segments": [
                        {
                            "title": "Opening",
                            "purpose": "Frame the question",
                            "target_duration_seconds": 300,
                            "lead_host_ids": ["host"],
                        }
                    ]
                }

        planner = EpisodePlannerService(database, Generator())
        plan = planner.build_plan(episode.id)
        with database.transaction() as connection:
            connection.execute("DELETE FROM segment_plans WHERE episode_plan_id=?", (plan.id,))
        app = DeeperDiveApp(service, episode_plan_controller=planner)
        app.current_project_id = project.id
        app.current_episode_id = episode.id
        async with app.run_test(size=(120, 50)) as pilot:
            app.action_navigate("plan")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, EpisodePlanScreen)
            screen.query_one("#segment-duration", Input).value = "bad"
            for action in (
                screen.action_approve_generate,
                screen.action_save_segment,
                screen.action_regenerate_segment,
            ):
                action()
                status = str(screen.query_one("#screen-status", Static).render())
                assert "The stored plan has no segments; regenerate the plan" in status
                assert "invalid literal" not in status

            screen.action_regenerate_plan()
            assert "Regenerated plan" in str(screen.query_one("#screen-status", Static).render())
            assert screen.plan is not None and screen.plan.segments

    asyncio.run(run())


async def _exercise_auto_generate(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    controller = FakePlanController()
    app = DeeperDiveApp(service, episode_plan_controller=controller)
    async with app.run_test(size=(120, 50)) as pilot:
        app.current_episode_id = "episode-1"
        app.action_navigate("plan")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodePlanScreen)
        screen.query_one("#auto-generate", Checkbox).value = True
        screen.action_approve_generate()
        await pilot.pause()
        assert app.plan_approved
        assert app.auto_generate_after_approval
        assert app.screen.id == "screen-generate"


def test_plan_screen_reports_an_approval_conflict_instead_of_crashing(tmp_path: Path) -> None:
    asyncio.run(_approval_conflict(tmp_path))


async def _approval_conflict(tmp_path: Path) -> None:
    from deeper_dive.episode_config import EpisodeConfigurationConflict

    class ConflictingController(FakePlanController):
        def approve_plan(self, episode_id: str, reviewed_plan_id: str | None = None) -> EpisodePlan:
            raise EpisodeConfigurationConflict("episode configuration changed; reload the plan")

    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    app = DeeperDiveApp(service, episode_plan_controller=ConflictingController())
    async with app.run_test(size=(120, 50)) as pilot:
        app.current_episode_id = "episode-1"
        app.action_navigate("plan")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, EpisodePlanScreen)
        screen.action_approve_generate()
        await pilot.pause()
        assert app.is_running
        assert not app.plan_approved
        assert app.screen is screen
