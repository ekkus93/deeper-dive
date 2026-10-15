"""Guided episode configuration, planning, and preflight workflow."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from typing import Protocol, cast

from textual.widget import Widget
from textual.widgets import Button, Input, Select, Static

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_planner import PlannedSegment
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.guided_episode_form import AUDIENCE_OPTIONS, EpisodeFormHelpers
from deeper_dive.guided_generation import GuidedGenerationMonitorScreen
from deeper_dive.wizard_transitions import (
    Transition,
    TransitionKind,
    WizardSaveOutcome,
    WizardSaveResult,
)


class _NavigationApp(Protocol):
    def action_navigate(self, destination: str) -> None: ...


class GuidedEpisodeWizard(EpisodeFormHelpers):
    """Carry New Deep Dive through durable episode setup, plan review, and preflight."""

    def _wizard_target(self, step: str) -> str | None:
        if step == "plan":
            ordinal = self._loaded_segment_ordinal
            return str(ordinal) if ordinal is not None else None
        return super()._wizard_target(step)

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
                list(AUDIENCE_OPTIONS),
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
        # Base-class handlers are dispatched by Textual itself (no super() call).
        if event.select.id == "guided-plan-segment-picker":
            value = event.value
            if not isinstance(value, str) or not value.isdigit():
                return
            if event.value != event.select.value:
                # Ignore stale queued events, including option-rebuild blank events,
                # rather than rehydrating over newer plan selection or edits.
                return
            ordinal = int(value)
            if (
                self._loaded_segment_ordinal is not None
                and ordinal != self._loaded_segment_ordinal
                and self._current_form_dirty()
            ):
                destination = ordinal
                self._assign_select(event.select, str(self._loaded_segment_ordinal))
                self._request_dirty_transition(
                    Transition(TransitionKind.PLAN_SELECT, str(destination))
                )
                return
            self._selected_segment_ordinal = ordinal
            self._load_selected_segment()
            self._remember_current_form()
        elif event.select.id == "guided-episode-duration":
            self._toggle_custom_duration()

    def _execute_custom_transition(self, transition: Transition) -> None:
        kind = transition.kind
        if kind is TransitionKind.PREFLIGHT_FIX:
            self.action_fix_preflight()
            return
        if kind is TransitionKind.GENERATION_START:
            self.action_generate_deep_dive()
            return
        if kind in {
            TransitionKind.PLAN_BUILD,
            TransitionKind.PLAN_REGENERATE,
            TransitionKind.PLAN_REGENERATE_SEGMENT,
        }:
            if kind is TransitionKind.PLAN_REGENERATE_SEGMENT:
                self.action_regenerate_plan_segment()
            else:
                self._run_plan_operation(
                    "build" if kind is TransitionKind.PLAN_BUILD else "regenerate"
                )
            return
        if kind is TransitionKind.PLAN_SELECT:
            ordinal = int(transition.argument or "")
            self._selected_segment_ordinal = ordinal
            picker = self.query_one("#guided-plan-segment-picker", Select)
            with picker.prevent(Select.Changed):
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
            return
        # Base-class handlers (WizardShell navigation buttons) are dispatched by
        # Textual itself; calling super() here would run them twice.

    def action_toggle_episode_advanced(self) -> None:
        self._episode_advanced = not self._episode_advanced
        self._toggle()
        self.set_status(
            "Advanced episode options shown."
            if self._episode_advanced
            else "Advanced episode options hidden."
        )

    def action_save_episode(self) -> bool:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            self.set_status("Choose and save episode hosts before configuring the episode.")
            return False
        service = EpisodeConfigurationService(
            self.context.composition.database_for_project(project_id)
        )
        try:
            if self._loaded_episode_id != episode_id or self._loaded_episode_config is None:
                raise ValueError(
                    "Episode settings are not loaded; reopen the episode before saving."
                )
            current = service.load_configuration(episode_id)
            if current.snapshot() != self._loaded_episode_config.snapshot():
                raise ValueError(
                    "Episode settings changed since this form was loaded. "
                    "Keep your edits and reload the episode before saving."
                )
            title = self.query_one("#guided-episode-title", Input).value.strip()
            focus = self.query_one("#guided-episode-focus", Input).value.strip()
            audience = self._select_value("#guided-episode-audience")
            depth = self._select_value("#guided-episode-depth")
            if not title or not focus or audience is None or depth is None:
                raise ValueError("title, main question, audience, and technical depth are required")
            config = replace(
                current,
                title=title,
                focus=focus,
                audience=audience,
                technical_depth=depth,
                target_duration_seconds=self._duration_seconds(current.target_duration_seconds),
                must_cover=self._csv("#guided-episode-must-cover"),
                avoid_topics=self._csv("#guided-episode-avoid"),
            )
            config.validate()
            saved = service.edit(
                episode_id, config, expected_revision=self._loaded_episode_revision
            )
        except (KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            safe = sanitize_exception_message(exc)
            self.query_one("#guided-episode-validation", Static).update(
                f"Fix episode settings: {safe}"
            )
            self.set_status("Episode settings need attention before continuing.")
            return False
        self._loaded_episode_config = config
        self._loaded_episode_revision = saved.config_json
        self.query_one("#guided-episode-validation", Static).update("")
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved episode settings through EpisodeConfigurationService.")
        return True

    def action_build_plan(self) -> None:
        self._run_plan_operation("build")

    def action_regenerate_plan(self) -> None:
        self._run_plan_operation("regenerate")

    def action_save_plan_segment(self) -> bool:
        if self._plan is None or self.context.episode_id is None:
            self.set_status("Build a plan before editing a segment.")
            return False
        try:
            segment = self._plan.segments[self._selected_segment_ordinal]
            title = self.query_one("#guided-plan-title", Input).value.strip()
            purpose = self.query_one("#guided-plan-purpose", Input).value.strip()
            duration = int(self.query_one("#guided-plan-duration", Input).value)
            revised = PlannedSegment(
                title=title,
                purpose=purpose,
                target_duration_seconds=duration,
                questions=segment.questions,
                evidence_ids=segment.evidence_ids,
                lead_host_ids=segment.lead_host_ids,
            )
            self._plan = self._planning_service().edit_segment(
                self.context.episode_id,
                self._selected_segment_ordinal,
                revised,
            )
        except (IndexError, KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self.set_error("Plan edit failed.", exc)
            return False
        self._render_plan()
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved the selected segment through EpisodePlannerService.")
        return True

    def action_regenerate_plan_segment(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self.context.state.current_step == "plan" and self._current_form_dirty():
            self._request_dirty_transition(Transition(TransitionKind.PLAN_REGENERATE_SEGMENT))
            return
        if self.context.episode_id is None:
            self.set_status("Build a plan before regenerating a segment.")
            return
        try:
            self._plan = self._planning_service().regenerate_segment(
                self.context.episode_id,
                self._selected_segment_ordinal,
            )
        except (IndexError, KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self.set_error("Segment regeneration failed.", exc)
            return
        self._render_plan()
        self._sync_text()
        self._remember_current_form()
        self.set_status("Regenerated the selected segment through EpisodePlannerService.")

    def action_fix_preflight(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self._current_form_dirty():
            self._request_dirty_transition(Transition(TransitionKind.PREFLIGHT_FIX))
            return
        if self._preflight is None or not self._preflight.blockers:
            self.set_status("No blocking preflight issue is currently available.")
            return
        code = self._preflight.blockers[0].code
        external = self._advanced_route_for_issue(code)
        if external is not None:
            cast(_NavigationApp, self.app).action_navigate(external)
            return
        step = self._route_for_issue(code)
        if step is None:
            self.set_status("Open Help for this blocker.")
            return
        self.context.state = self.context.state.moved_to(step)
        self._sync_text()
        self._toggle()
        self.set_status(f"Returned to {step.replace('-', ' ')} to repair the blocker.")

    def action_generate_deep_dive(self) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self._current_form_dirty():
            self._request_dirty_transition(Transition(TransitionKind.GENERATION_START))
            return
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            self.set_status("Complete episode setup before generating.")
            return
        try:
            result = GenerationStartService(self.context.composition).start(
                project_id,
                episode_id,
            )
        except (KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self.set_error("Generation could not start.", exc)
            return
        self.context.run_id = result.run.id
        app = self.app
        if hasattr(app, "current_project_id"):
            app.current_project_id = project_id
        if hasattr(app, "current_episode_id"):
            app.current_episode_id = episode_id
        if hasattr(app, "current_run_id"):
            app.current_run_id = result.run.id
        self.set_status(
            "Generation run is ready: "
            + ("created a new durable run." if result.created else "reused the active durable run.")
        )
        cast(_NavigationApp, app).action_navigate("monitor")
        app.call_after_refresh(self._start_guided_generation)

    def _start_guided_generation(self) -> None:
        screen = self.app.screen
        if isinstance(screen, GuidedGenerationMonitorScreen):
            screen.start_background_generation()

    def _run_plan_operation(self, operation: str) -> None:
        if self.busy or self._exit_confirmation_pending:
            return
        if self.context.state.current_step == "plan" and self._current_form_dirty():
            self._request_dirty_transition(
                Transition(
                    TransitionKind.PLAN_BUILD
                    if operation == "build"
                    else TransitionKind.PLAN_REGENERATE
                )
            )
            return
        episode_id = self.context.episode_id
        if episode_id is None:
            self.set_status("Save episode settings before building a plan.")
            return
        self.set_busy(True, "Building the production episode plan…")
        try:
            planner = self._planning_service()
            self._plan = (
                planner.regenerate_plan(episode_id)
                if operation == "regenerate"
                else planner.build_plan(episode_id)
            )
            self._selected_segment_ordinal = 0
        except (KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self.set_busy(False)
            self.set_error("Episode planning failed.", exc)
            return
        self.set_busy(False)
        self._render_plan()
        self._sync_text()
        self._remember_current_form()
        self.set_status(
            "Regenerated the production episode plan."
            if operation == "regenerate"
            else "Built the production episode plan."
        )
