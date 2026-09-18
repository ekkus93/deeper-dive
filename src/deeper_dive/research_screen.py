"""Research policy, gap, and candidate workflow for the Textual UI."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Select, Static

from deeper_dive.research_candidates import CandidateOutcome
from deeper_dive.research_gaps import ResearchGap
from deeper_dive.research_policy import ResearchControls, ResearchMode, ResearchPolicy


class ResearchController(Protocol):
    """Presentation boundary for research orchestration."""

    def policy(self, project_id: str) -> ResearchPolicy: ...
    def save_policy(self, project_id: str, policy: ResearchPolicy, focus: str) -> None: ...
    def focus(self, project_id: str) -> str: ...
    def analyze(self, project_id: str, focus: str) -> tuple[ResearchGap, ...]: ...
    def gaps(self, project_id: str) -> tuple[ResearchGap, ...]: ...
    def set_gap_status(self, project_id: str, gap_id: str, status: str) -> None: ...
    def research(
        self, project_id: str, gap_ids: tuple[str, ...]
    ) -> tuple[CandidateOutcome, ...]: ...
    def outcomes(self, project_id: str) -> tuple[CandidateOutcome, ...]: ...


class ResearchScreen(Screen[None]):
    """Inspect and drive supplemental research without hiding provenance."""

    CONTROL_FIELDS = (
        "find_newer_research",
        "contradictory_evidence",
        "missing_citations",
        "prefer_primary_sources",
        "replication_review_evidence",
        "background_context",
        "permit_general_interest",
    )

    def __init__(self) -> None:
        super().__init__(id="screen-research")
        self.selected_gap_id: str | None = None

    @property
    def _app(self):
        return self.app

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), id=f"nav-{key}", name=f"nav:{key}")
        with VerticalScroll(id="content"):
            yield Label("Research", id="screen-title")
            yield Select(
                [(mode.value.title(), mode.value) for mode in ResearchMode],
                value=ResearchMode.USEFUL.value,
                id="research-policy",
            )
            for field in self.CONTROL_FIELDS:
                yield Checkbox(field.replace("_", " ").title(), value=True, id=f"research-{field}")
            yield Input(placeholder="Research focus", id="research-focus")
            yield Button("Save Policy", id="research-save", name="save")
            yield Button("Analyze Corpus / Find Gaps", id="research-analyze", name="analyze")
            yield Static("No gaps analyzed.", id="research-gaps")
            yield Input(placeholder="Selected gap ID", id="research-gap-id")
            yield Button("Search Gap", id="research-search", name="search")
            yield Button("Ignore Gap", id="research-ignore", name="ignore")
            yield Button("Research All Open", id="research-all", name="all")
            yield Static("Progress: idle", id="research-progress")
            yield Static("No candidate outcomes.", id="research-candidates")
            yield Button("View Supplemental Sources", id="research-sources", name="sources")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_research()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name or ""
        if action.startswith("nav:"):
            cast(object, self.app).action_navigate(action.split(":", 1)[1])  # type: ignore[attr-defined]
        elif action == "save":
            self.action_save()
        elif action == "analyze":
            self.action_analyze()
        elif action == "search":
            self.action_search()
        elif action == "ignore":
            self.action_ignore()
        elif action == "all":
            self.action_research_all()
        elif action == "sources":
            cast(object, self.app).action_navigate("sources")  # type: ignore[attr-defined]

    def action_save(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            return
        policy = self._policy_from_widgets()
        focus = self.query_one("#research-focus", Input).value.strip()
        self._controller().save_policy(project_id, policy, focus)
        self._status("Research policy saved")

    def action_analyze(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            return
        self.query_one("#research-progress", Static).update("Progress: analyzing corpus")
        focus = self.query_one("#research-focus", Input).value.strip()
        gaps = self._controller().analyze(project_id, focus)
        self.selected_gap_id = gaps[0].id if gaps else None
        self.refresh_research(f"Found {len(gaps)} research gaps")

    def action_search(self) -> None:
        project_id = self._project_id()
        gap_id = self._selected_gap()
        if project_id is None or gap_id is None:
            return
        self.query_one("#research-progress", Static).update(f"Progress: researching {gap_id}")
        outcomes = self._controller().research(project_id, (gap_id,))
        self.refresh_research(self._outcome_status(outcomes))

    def action_ignore(self) -> None:
        project_id = self._project_id()
        gap_id = self._selected_gap()
        if project_id is None or gap_id is None:
            return
        self._controller().set_gap_status(project_id, gap_id, "ignored")
        self.refresh_research(f"Ignored gap {gap_id}")

    def action_research_all(self) -> None:
        project_id = self._project_id()
        if project_id is None:
            return
        gap_ids = tuple(
            gap.id for gap in self._controller().gaps(project_id) if gap.status == "open"
        )
        self.query_one("#research-progress", Static).update(
            f"Progress: researching {len(gap_ids)} open gaps"
        )
        outcomes = self._controller().research(project_id, gap_ids) if gap_ids else ()
        self.refresh_research(self._outcome_status(outcomes))

    def refresh_research(self, status: str = "Ready") -> None:
        project_id = self._project_id(quiet=True)
        if project_id is None:
            self._status("Open a project first")
            return
        controller = self._controller()
        policy = controller.policy(project_id)
        self.query_one("#research-policy", Select).value = policy.mode.value
        for field in self.CONTROL_FIELDS:
            self.query_one(f"#research-{field}", Checkbox).value = bool(
                getattr(policy.controls, field)
            )
        self.query_one("#research-focus", Input).value = controller.focus(project_id)
        gaps = controller.gaps(project_id)
        if self.selected_gap_id is None and gaps:
            self.selected_gap_id = gaps[0].id
        self.query_one("#research-gaps", Static).update(self._gap_text(gaps))
        self.query_one("#research-candidates", Static).update(
            self._candidate_text(controller.outcomes(project_id))
        )
        self.query_one("#research-progress", Static).update("Progress: idle")
        self._status(status)

    def _controller(self) -> ResearchController:
        return cast(ResearchController, getattr(self.app, "research_controller"))

    def _project_id(self, *, quiet: bool = False) -> str | None:
        project_id = cast(str | None, getattr(self.app, "current_project_id", None))
        if project_id is None and not quiet:
            self._status("Open a project before researching")
        return project_id

    def _selected_gap(self) -> str | None:
        typed = self.query_one("#research-gap-id", Input).value.strip()
        gap_id = typed or self.selected_gap_id
        if gap_id is None:
            self._status("No research gap selected")
        return gap_id

    def _policy_from_widgets(self) -> ResearchPolicy:
        value = self.query_one("#research-policy", Select).value
        mode = ResearchMode(str(value))
        values = {
            field: self.query_one(f"#research-{field}", Checkbox).value
            for field in self.CONTROL_FIELDS
        }
        return ResearchPolicy(mode, ResearchControls(**values))

    @staticmethod
    def _gap_text(gaps: tuple[ResearchGap, ...]) -> str:
        if not gaps:
            return "No gaps analyzed."
        return "\n".join(
            f"{gap.id} | P{gap.priority} | {gap.status} | {gap.category.value} | {gap.rationale}"
            for gap in gaps
        )

    @staticmethod
    def _candidate_text(outcomes: tuple[CandidateOutcome, ...]) -> str:
        if not outcomes:
            return "No candidate outcomes."
        return "\n".join(
            f"{'accepted' if item.accepted else 'rejected'} | {item.title} | "
            f"authority {item.authority_score} | gap {item.gap_id} | {item.reason}"
            for item in outcomes
        )

    @staticmethod
    def _outcome_status(outcomes: tuple[CandidateOutcome, ...]) -> str:
        accepted = sum(item.accepted for item in outcomes)
        return f"Research complete: {accepted} accepted, {len(outcomes) - accepted} rejected"

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
