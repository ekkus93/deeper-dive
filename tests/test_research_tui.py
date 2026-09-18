from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.research_candidates import CandidateOutcome
from deeper_dive.research_gaps import ResearchGap, ResearchGapCategory
from deeper_dive.research_policy import ResearchPolicy
from deeper_dive.research_screen import ResearchScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp, SourcesScreen


class FakeResearchController:
    def __init__(self, service: DeeperDiveService) -> None:
        self.service = service
        self._policy = ResearchPolicy()
        self._focus = ""
        self._gaps: tuple[ResearchGap, ...] = ()
        self._outcomes: tuple[CandidateOutcome, ...] = ()

    def policy(self, project_id: str) -> ResearchPolicy:
        return self._policy

    def save_policy(self, project_id: str, policy: ResearchPolicy, focus: str) -> None:
        self._policy = policy
        self._focus = focus

    def focus(self, project_id: str) -> str:
        return self._focus

    def analyze(self, project_id: str, focus: str) -> tuple[ResearchGap, ...]:
        self._focus = focus
        self._gaps = (
            ResearchGap(
                "gap-1",
                project_id,
                ResearchGapCategory.RECENCY,
                "Find newer orchard yield evidence",
                5,
            ),
            ResearchGap(
                "gap-2",
                project_id,
                ResearchGapCategory.MISSING_CONTEXT,
                "Add regional context",
                3,
            ),
        )
        return self._gaps

    def gaps(self, project_id: str) -> tuple[ResearchGap, ...]:
        return self._gaps

    def set_gap_status(self, project_id: str, gap_id: str, status: str) -> None:
        self._gaps = tuple(
            replace(gap, status=status) if gap.id == gap_id else gap for gap in self._gaps
        )

    def research(self, project_id: str, gap_ids: tuple[str, ...]) -> tuple[CandidateOutcome, ...]:
        if not gap_ids:
            return ()
        source = self.service.add_pasted_source(
            project_id,
            "Supplemental orchard study",
            "A newer orchard study reports regional yield evidence.",
            origin="supplemental",
        )
        outcome = CandidateOutcome(
            "candidate-1",
            project_id,
            gap_ids[0],
            "https://example.org/study",
            source.title,
            True,
            f"accepted for gap {gap_ids[0]}: newer evidence",
            2,
            source.content_hash or "hash",
        )
        self._outcomes += (outcome,)
        self.set_gap_status(project_id, gap_ids[0], "researched")
        return (outcome,)

    def outcomes(self, project_id: str) -> tuple[CandidateOutcome, ...]:
        return self._outcomes


def test_research_tui_gap_ignore_research_and_provenance(tmp_path: Path) -> None:
    asyncio.run(_research_workflow(tmp_path))


async def _research_workflow(tmp_path: Path) -> None:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("Research project")
    controller = FakeResearchController(service)
    app = DeeperDiveApp(service, research_controller=controller)
    app.current_project_id = project.id
    app.current_project_name = project.name

    async with app.run_test(size=(100, 40)) as pilot:
        app.action_navigate("research")
        await pilot.pause()
        assert isinstance(app.screen, ResearchScreen)
        screen = app.screen
        screen.query_one("#research-focus", Input).value = "orchard yields"
        screen.action_save()
        assert controller.focus(project.id) == "orchard yields"

        screen.action_analyze()
        assert "Find newer orchard" in _text(screen, "#research-gaps")
        screen.query_one("#research-gap-id", Input).value = "gap-2"
        screen.action_ignore()
        assert controller.gaps(project.id)[1].status == "ignored"

        screen.query_one("#research-gap-id", Input).value = "gap-1"
        screen.action_search()
        assert "accepted" in _text(screen, "#research-candidates")
        assert "gap-1" in _text(screen, "#research-candidates")

        app.action_navigate("sources")
        await pilot.pause()
        assert isinstance(app.screen, SourcesScreen)
        assert "Supplemental orchard study" in _text(app.screen, "#source-list")
        assert "Origin: supplemental" in _text(app.screen, "#source-details")


def _text(screen: ResearchScreen | SourcesScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())
