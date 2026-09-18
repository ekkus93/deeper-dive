from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from textual.widgets import Checkbox, Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_plan_screen import EpisodePlanScreen
from deeper_dive.episode_planner import EpisodePlan, PlannedSegment
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
                PlannedSegment("Evidence", "Test the claim", 600, ("What evidence?",), (), ("host-2",)),
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

    def approve_plan(self, episode_id: str) -> EpisodePlan:
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
