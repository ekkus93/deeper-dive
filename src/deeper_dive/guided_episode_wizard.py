"""Guided episode configuration, planning, and preflight workflow."""

from __future__ import annotations

from dataclasses import replace
from typing import Protocol, cast

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlan, EpisodePlannerService, PlannedSegment
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.guided_host_wizard import GuidedHostWizard
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.model_roles import ModelRole
from deeper_dive.plan_validity import evaluate_episode_plan
from deeper_dive.preflight import PreflightReport
from deeper_dive.research_policy import ResearchPolicyStore
from deeper_dive.wizard_shell import WizardSaveOutcome, WizardSaveResult


class _NavigationApp(Protocol):
    def action_navigate(self, destination: str) -> None: ...


class GuidedEpisodeWizard(GuidedHostWizard):
    """Carry New Deep Dive through durable episode setup, plan review, and preflight."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._plan: EpisodePlan | None = None
        self._selected_segment_ordinal = 0
        self._loaded_segment_ordinal: int | None = None
        self._ignore_plan_picker_value: str | None = None
        self._preflight: PreflightReport | None = None
        self._episode_advanced = False

    def _save_dirty_step(self) -> WizardSaveResult:
        step = self.context.state.current_step
        self._last_form_status = ""
        if step == "project":
            return WizardSaveResult.from_bool(self.action_create_project())
        if step == "sources":
            # Importing a file/URL must not implicitly discard an unrelated,
            # incomplete pasted-source form when Save changes and exit is chosen.
            title = self.query_one("#guided-source-title", Input).value.strip()
            body = self.query_one("#guided-source-text", Input).value.strip()
            if bool(title) != bool(body):
                self.set_status("Provide both pasted-source title and text, or discard edits.")
                return WizardSaveResult(WizardSaveOutcome.FAILED)
            actions = (
                ("#guided-source-text", self.action_add_pasted_source),
                ("#guided-source-paths", self.action_add_file_sources),
                ("#guided-source-urls", self.action_add_url_sources),
            )
            invoked = False
            saved_any = False
            for selector, action in actions:
                if self.query_one(selector, Input).value.strip():
                    invoked = True
                    if action():
                        saved_any = True
                        continue
                    return WizardSaveResult(
                        WizardSaveOutcome.PARTIAL if saved_any else WizardSaveOutcome.FAILED,
                        "Some source input was saved, but unresolved edits remain. "
                        "Review the retained fields and retry or discard them explicitly."
                        if saved_any
                        else "",
                    )
            if not invoked and title:
                return WizardSaveResult.from_bool(self.action_add_pasted_source())
            return WizardSaveResult(WizardSaveOutcome.SAVED if invoked else WizardSaveOutcome.NOOP)
        if step == "research":
            return WizardSaveResult.from_bool(self.action_save_research())
        if step == "hosts":
            profile_dirty = self._host_profile_dirty()
            order_dirty = self._host_order_dirty()
            profile_saved = False
            if profile_dirty:
                if self._selected_host_record() is None:
                    if not self.action_create_host():
                        return WizardSaveResult(WizardSaveOutcome.FAILED)
                elif not self.action_save_host():
                    return WizardSaveResult(WizardSaveOutcome.FAILED)
                profile_saved = True
            if order_dirty and not self.action_save_host_order():
                return WizardSaveResult(
                        WizardSaveOutcome.PARTIAL if profile_saved else WizardSaveOutcome.FAILED,
                        "Host profile changes were saved, but episode host membership/order "
                        "was not. The remaining order edit is still pending; retry or discard it."
                        if profile_saved
                        else "",
                    )
            if profile_saved or order_dirty:
                return WizardSaveResult(WizardSaveOutcome.SAVED)
            return WizardSaveResult(WizardSaveOutcome.NOOP)
        if step == "episode":
            return WizardSaveResult.from_bool(self.action_save_episode())
        if step == "plan":
            return WizardSaveResult.from_bool(self.action_save_plan_segment())
        return super()._save_dirty_step()

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            *super().step_controls(),
            Input(placeholder="Episode title", id="guided-episode-title"),
            Input(placeholder="Main question / focus", id="guided-episode-focus"),
            Select(
                [
                    ("10 minutes", "10"),
                    ("20 minutes", "20"),
                    ("30 minutes", "30"),
                    ("Custom", "custom"),
                ],
                value="20",
                allow_blank=False,
                id="guided-episode-duration",
            ),
            Input(placeholder="Custom duration in minutes", id="guided-episode-custom-duration"),
            Select(
                [
                    ("General audience", "general"),
                    ("Technical audience", "technical"),
                    ("Expert audience", "expert"),
                ],
                value="general",
                allow_blank=False,
                id="guided-episode-audience",
            ),
            Button(
                "Advanced Options",
                id="guided-episode-advanced",
                name="toggle-episode-advanced",
            ),
            Select(
                [
                    ("Accessible", "accessible"),
                    ("Balanced", "balanced"),
                    ("Deep", "deep"),
                ],
                value="balanced",
                allow_blank=False,
                id="guided-episode-depth",
            ),
            Input(placeholder="Must-cover topics, comma separated", id="guided-episode-must-cover"),
            Input(placeholder="Avoid topics, comma separated", id="guided-episode-avoid"),
            Static("", id="guided-episode-validation", markup=False),
            Button("Save Episode Settings", id="guided-episode-save", name="save-episode"),
            Static("No plan loaded.", id="guided-plan-summary"),
            Select([], allow_blank=True, id="guided-plan-segment-picker"),
            Input(placeholder="Segment title", id="guided-plan-title"),
            Input(placeholder="Segment purpose", id="guided-plan-purpose"),
            Input(placeholder="Segment duration seconds", id="guided-plan-duration"),
            Button("Build Plan", id="guided-plan-build", name="build-plan"),
            Button("Save Segment Edit", id="guided-plan-save-segment", name="save-plan-segment"),
            Button(
                "Regenerate Segment",
                id="guided-plan-regenerate-segment",
                name="regenerate-plan-segment",
            ),
            Button("Regenerate Plan", id="guided-plan-regenerate", name="regenerate-plan"),
            Static("Preflight has not run.", id="guided-preflight-summary"),
            Button("Check Readiness", id="guided-preflight-check", name="check-preflight"),
            Button("Fix First Blocker", id="guided-preflight-fix", name="fix-preflight"),
            Button(
                "Generate Deep Dive",
                id="guided-preflight-generate",
                name="generate-deep-dive",
                variant="primary",
            ),
        )

    def step_content(self, step_key: str) -> str:
        if step_key == "episode":
            return (
                "Set the episode title, focus, duration, audience, and optional advanced "
                "content constraints. Saving writes through EpisodeConfigurationService."
            )
        if step_key == "plan":
            return (
                "Build and review the durable episode plan through EpisodePlannerService. "
                "You can edit the selected segment or regenerate while the production plan "
                "remains mutable."
            )
        if step_key == "preflight":
            return (
                "Ready to Generate uses the same GenerationStartService preflight and "
                "duplicate-safe run creation used by production surfaces."
            )
        return super().step_content(step_key)

    def on_mount(self) -> None:
        super().on_mount()
        self._load_episode_form()
        self._refresh_plan()
        self._refresh_preflight()
        self._toggle()
        self._remember_current_form()

    def on_screen_resume(self) -> None:
        """A previously mounted wizard must reload production state when re-entered."""
        if not self.is_mounted:
            return
        if self._current_form_dirty():
            self.set_status("Unsaved changes remain; save or discard them before reloading.")
            return
        self.context.state = self.navigator.recovered_state()
        self._selected_host_ids = []
        self._load_episode_host_order()
        self._refresh_sources()
        self._refresh_hosts()
        self._load_episode_form()
        self._refresh_plan()
        self._refresh_preflight()
        self._sync_text()
        self._toggle()
        self._remember_current_form()

    def action_continue(self) -> bool:
        if not super().action_continue():
            return False
        self._load_episode_form()
        self._refresh_plan()
        self._refresh_preflight()
        self._toggle()
        self._remember_current_form()
        return True

    def action_back(self) -> bool:
        if not super().action_back():
            return False
        self._load_episode_form()
        self._refresh_plan()
        self._refresh_preflight()
        self._toggle()
        self._remember_current_form()
        return True

    def on_select_changed(self, event: Select.Changed) -> None:
        super().on_select_changed(event)
        if event.select.id == "guided-plan-segment-picker":
            value = event.value
            if not isinstance(value, str) or not value.isdigit():
                return
            if event.value != event.select.value:
                # Ignore stale queued events, including option-rebuild blank events,
                # rather than rehydrating over newer plan selection or edits.
                return
            if value == self._ignore_plan_picker_value:
                self._ignore_plan_picker_value = None
                return
            ordinal = int(value)
            if (
                self._loaded_segment_ordinal is not None
                and ordinal != self._loaded_segment_ordinal
                and self._current_form_dirty()
            ):
                destination = ordinal
                self._ignore_plan_picker_value = str(self._loaded_segment_ordinal)
                event.select.value = str(self._loaded_segment_ordinal)  # type: ignore[assignment]
                self._request_dirty_transition(f"plan-select:{destination}")
                return
            self._selected_segment_ordinal = ordinal
            self._load_selected_segment()
            self._remember_current_form()
        elif event.select.id == "guided-episode-duration":
            self._toggle_custom_duration()

    def _execute_custom_transition(self, transition: str) -> None:
        if transition.startswith("plan-select:"):
            ordinal = int(transition.split(":", 1)[1])
            self._selected_segment_ordinal = ordinal
            picker = self.query_one("#guided-plan-segment-picker", Select)
            picker.value = str(ordinal)
            self._load_selected_segment()
            self._remember_current_form()
            return
        super()._execute_custom_transition(transition)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handlers = {
            "toggle-episode-advanced": self.action_toggle_episode_advanced,
            "save-episode": self.action_save_episode,
            "build-plan": self.action_build_plan,
            "save-plan-segment": self.action_save_plan_segment,
            "regenerate-plan-segment": self.action_regenerate_plan_segment,
            "regenerate-plan": self.action_regenerate_plan,
            "check-preflight": self.action_check_preflight,
            "fix-preflight": self.action_fix_preflight,
            "generate-deep-dive": self.action_generate_deep_dive,
        }
        handler = handlers.get(event.button.name or "")
        if handler is not None:
            event.stop()
            handler()
