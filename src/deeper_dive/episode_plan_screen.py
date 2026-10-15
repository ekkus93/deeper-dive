"""Episode plan review screen; generation remains gated on explicit approval."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Static

from deeper_dive.diagnostics import redact, sanitize_exception_message
from deeper_dive.episode_planner import EpisodePlan, PlannedSegment
from deeper_dive.screen_guard import report_service_errors

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp


# Everything a planner/config/run service call can raise for a recoverable reason;
# typed episode errors subclass ValueError. Never let these terminate the app.
_SERVICE_ERRORS = (KeyError, IndexError, OSError, RuntimeError, ValueError, sqlite3.Error)


_RELOAD_HINT = " Choose Reload Plan to see the stored plan."


class EpisodePlanController(Protocol):
    def load_plan(self, episode_id: str) -> EpisodePlan: ...
    def regenerate_plan(self, episode_id: str) -> EpisodePlan: ...
    def regenerate_segment(self, episode_id: str, ordinal: int) -> EpisodePlan: ...
    def edit_segment(
        self, episode_id: str, ordinal: int, segment: PlannedSegment
    ) -> EpisodePlan: ...
    def approve_plan(self, episode_id: str, reviewed_plan_id: str | None = None) -> EpisodePlan: ...


class EpisodePlanScreen(Screen[None]):
    """Review/edit a structured plan before any dialogue or TTS generation."""

    def __init__(self) -> None:
        super().__init__(id="screen-plan")
        self.selected_ordinal = 0
        self.plan: EpisodePlan | None = None

    @property
    def _app(self) -> DeeperDiveApp:
        return cast("DeeperDiveApp", self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with VerticalScroll(id="content"):
            yield Label("Episode Plan", id="screen-title")
            yield Static("Review and change the plan before generation.", id="screen-description")
            yield Static("No plan loaded", id="segment-list")
            yield Input(value="0", placeholder="Selected segment number", id="segment-number")
            yield Input(placeholder="Segment title", id="segment-title")
            yield Input(placeholder="Purpose", id="segment-purpose")
            yield Input(placeholder="Duration seconds", id="segment-duration")
            yield Input(placeholder="Questions, comma separated", id="segment-questions")
            yield Input(placeholder="Evidence IDs, comma separated", id="segment-evidence")
            yield Input(placeholder="Lead host IDs, comma separated", id="segment-hosts")
            yield Button("Reload Plan", id="action-reload-plan", name="reload-plan")
            yield Button("Select Segment", id="action-select-segment", name="select-segment")
            yield Button("Save Segment", id="action-save-segment", name="save-segment")
            yield Button("Regenerate Segment", id="action-regenerate-segment", name="regen-segment")
            yield Button("Regenerate Plan", id="action-regenerate-plan", name="regen-plan")
            yield Checkbox("Auto-generate after approval", id="auto-generate")
            yield Button(
                "Approve and Generate", id="action-approve-generate", name="approve-generate"
            )
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_plan()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        if name == "select-segment":
            self.action_select_segment()
        elif name == "reload-plan":
            self.action_reload_plan()
        elif name == "save-segment":
            self.action_save_segment()
        elif name == "regen-segment":
            self.action_regenerate_segment()
        elif name == "regen-plan":
            self.action_regenerate_plan()
        elif name == "approve-generate":
            self.action_approve_generate()
        elif name:
            self._app.action_navigate(name)

    @report_service_errors("Plan not reloaded")
    def action_reload_plan(self) -> None:
        """Show the stored plan without regenerating it (e.g. after a conflict).

        The stored plan wins: unsaved segment edits are replaced, and the status says
        so when there were any.
        """

        discarded = self._segment_inputs_differ()
        if self.refresh_plan():
            self._status(
                "Reloaded the stored plan; unsaved segment edits were discarded"
                if discarded
                else "Reloaded the stored plan"
            )

    def _segment_inputs_differ(self) -> bool:
        """Whether the segment inputs hold edits that differ from the loaded segment."""

        if self.plan is None or not self.plan.segments:
            return False
        segment = self.plan.segments[min(self.selected_ordinal, len(self.plan.segments) - 1)]
        shown = (
            ("#segment-title", segment.title),
            ("#segment-purpose", segment.purpose),
            ("#segment-duration", str(segment.target_duration_seconds)),
            ("#segment-questions", ", ".join(segment.questions)),
            ("#segment-evidence", ", ".join(segment.evidence_ids)),
            ("#segment-hosts", ", ".join(segment.lead_host_ids)),
        )
        return any(self.query_one(selector, Input).value != value for selector, value in shown)

    def refresh_plan(self) -> bool:
        episode_id = self._app.current_episode_id
        controller = self._app.episode_plan_controller
        if episode_id is None or controller is None:
            self._status("Build an episode plan before opening plan review")
            return False
        try:
            self.plan = controller.load_plan(episode_id)
        except KeyError:
            self._status("No plan exists for this episode")
            return False
        except _SERVICE_ERRORS as exc:
            self._status(f"Plan could not be loaded: {sanitize_exception_message(exc)}")
            return False
        if self.selected_ordinal >= len(self.plan.segments):
            self.selected_ordinal = 0
        self._render_plan()
        if not self.plan.segments:
            self._clear_selected()
            self._status("The stored plan has no segments; regenerate the plan")
            return False
        self._load_selected()
        return True

    def action_select_segment(self) -> None:
        if self.plan is None:
            return
        try:
            ordinal = int(self.query_one("#segment-number", Input).value) - 1
        except ValueError:
            self._status("Segment number must be an integer")
            return
        if ordinal < 0 or ordinal >= len(self.plan.segments):
            self._status("Segment number is out of range")
            return
        self.selected_ordinal = ordinal
        self._load_selected()
        self._status(f"Selected segment {ordinal + 1}")

    def action_save_segment(self) -> None:
        context = self._plan_context()
        if context is None:
            return
        episode_id, controller = context
        try:
            duration = int(self.query_one("#segment-duration", Input).value)
            segment = PlannedSegment(
                title=self.query_one("#segment-title", Input).value.strip(),
                purpose=self.query_one("#segment-purpose", Input).value.strip(),
                target_duration_seconds=duration,
                questions=self._csv("#segment-questions"),
                evidence_ids=self._csv("#segment-evidence"),
                lead_host_ids=self._csv("#segment-hosts"),
            )
            self.plan = controller.edit_segment(episode_id, self.selected_ordinal, segment)
        except ValueError as exc:
            self._status(sanitize_exception_message(exc))
            return
        except _SERVICE_ERRORS as exc:
            self._status(f"Segment not saved: {sanitize_exception_message(exc)}{_RELOAD_HINT}")
            return
        self._render_plan()
        self._load_selected()
        self._status(f"Saved segment {self.selected_ordinal + 1}")

    def action_regenerate_segment(self) -> None:
        context = self._plan_context()
        if context is None:
            return
        episode_id, controller = context
        try:
            plan = controller.regenerate_segment(episode_id, self.selected_ordinal)
        except _SERVICE_ERRORS as exc:
            self._status(
                f"Segment not regenerated: {sanitize_exception_message(exc)}{_RELOAD_HINT}"
            )
            return
        self.plan = plan
        self._render_plan()
        self._load_selected()
        self._status(f"Regenerated segment {self.selected_ordinal + 1}")

    def action_regenerate_plan(self) -> None:
        context = self._plan_context(allow_empty=True)
        if context is None:
            return
        episode_id, controller = context
        try:
            plan = controller.regenerate_plan(episode_id)
        except _SERVICE_ERRORS as exc:
            self._status(f"Plan not regenerated: {sanitize_exception_message(exc)}{_RELOAD_HINT}")
            return
        self.plan = plan
        self.selected_ordinal = 0
        self._render_plan()
        self._load_selected()
        self._status("Regenerated plan; review it before approval")

    def action_approve_generate(self) -> None:
        context = self._plan_context()
        if context is None:
            return
        episode_id, controller = context
        reviewed = self.plan
        assert reviewed is not None  # _plan_context returned a context
        try:
            self.plan = controller.approve_plan(episode_id, reviewed_plan_id=reviewed.id)
        except _SERVICE_ERRORS as exc:
            # Includes EpisodeConfigurationConflict: the episode changed or the plan
            # was replaced since it was loaded. Nothing was approved.
            self._status(f"Plan not approved: {sanitize_exception_message(exc)}{_RELOAD_HINT}")
            return
        auto = self.query_one("#auto-generate", Checkbox).value
        self._app.plan_approved = True
        self._app.auto_generate_after_approval = auto
        if auto:
            self._status("Plan approved; generation may start")
            self._app.action_navigate("generate")
        else:
            self._status("Plan approved; generation remains explicitly gated")

    def _plan_context(
        self, *, allow_empty: bool = False
    ) -> tuple[str, EpisodePlanController] | None:
        if self.plan is None or self._app.current_episode_id is None:
            self._status("No plan loaded")
            return None
        if not self.plan.segments and not allow_empty:
            self._status("The stored plan has no segments; regenerate the plan")
            return None
        controller = self._app.episode_plan_controller
        if controller is None:
            self._status("Episode planner is unavailable")
            return None
        return self._app.current_episode_id, controller

    def _render_plan(self) -> None:
        assert self.plan is not None
        rows = []
        for ordinal, segment in enumerate(self.plan.segments):
            marker = "*" if ordinal == self.selected_ordinal else " "
            rows.append(
                f"{marker} {ordinal + 1}. {segment.title} | {segment.target_duration_seconds}s | "
                f"purpose={segment.purpose} | questions={', '.join(segment.questions) or 'none'} | "
                f"evidence={', '.join(segment.evidence_ids) or 'none'} | "
                f"leads={', '.join(segment.lead_host_ids) or 'none'}"
            )
        self.query_one("#segment-list", Static).update(
            f"Total estimate: {self.plan.target_duration_seconds}s\n" + "\n".join(rows)
        )

    def _clear_selected(self) -> None:
        for selector in (
            "#segment-title",
            "#segment-purpose",
            "#segment-duration",
            "#segment-questions",
            "#segment-evidence",
            "#segment-hosts",
        ):
            self.query_one(selector, Input).value = ""
        self.query_one("#segment-number", Input).value = ""

    def _load_selected(self) -> None:
        assert self.plan is not None
        if not self.plan.segments:
            self._clear_selected()
            return
        self.selected_ordinal = min(self.selected_ordinal, len(self.plan.segments) - 1)
        segment = self.plan.segments[self.selected_ordinal]
        self.query_one("#segment-number", Input).value = str(self.selected_ordinal + 1)
        self.query_one("#segment-title", Input).value = segment.title
        self.query_one("#segment-purpose", Input).value = segment.purpose
        self.query_one("#segment-duration", Input).value = str(segment.target_duration_seconds)
        self.query_one("#segment-questions", Input).value = ", ".join(segment.questions)
        self.query_one("#segment-evidence", Input).value = ", ".join(segment.evidence_ids)
        self.query_one("#segment-hosts", Input).value = ", ".join(segment.lead_host_ids)

    def _csv(self, selector: str) -> tuple[str, ...]:
        return tuple(
            value.strip()
            for value in self.query_one(selector, Input).value.split(",")
            if value.strip()
        )

    def _status(self, value: str) -> None:
        self.query_one("#screen-status", Static).update(str(redact(f"Status: {value}")))
