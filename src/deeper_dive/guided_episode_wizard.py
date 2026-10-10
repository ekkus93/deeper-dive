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


class _NavigationApp(Protocol):
    def action_navigate(self, destination: str) -> None: ...


class GuidedEpisodeWizard(GuidedHostWizard):
    """Carry New Deep Dive through durable episode setup, plan review, and preflight."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._plan: EpisodePlan | None = None
        self._selected_segment_ordinal = 0
        self._preflight: PreflightReport | None = None
        self._episode_advanced = False

    def _save_dirty_step(self) -> bool:
        step = self.context.state.current_step
        self._last_form_status = ""
        if step == "project":
            self.action_create_project()
            return self._last_form_status.startswith("Created project ")
        if step == "sources":
            # Importing a file/URL must not implicitly discard an unrelated,
            # incomplete pasted-source form when Save changes and exit is chosen.
            title = self.query_one("#guided-source-title", Input).value.strip()
            body = self.query_one("#guided-source-text", Input).value.strip()
            if bool(title) != bool(body):
                self.set_status("Provide both pasted-source title and text, or discard edits.")
                return False
            actions: tuple[tuple[str, str], ...] = (
                ("#guided-source-text", "action_add_pasted_source"),
                ("#guided-source-paths", "action_add_file_sources"),
                ("#guided-source-urls", "action_add_url_sources"),
            )
            invoked = False
            for selector, name in actions:
                if self.query_one(selector, Input).value.strip():
                    invoked = True
                    getattr(self, name)()
                    if not self._last_form_status.startswith("Imported "):
                        return False
            if not invoked and self.query_one("#guided-source-title", Input).value.strip():
                self.action_add_pasted_source()
                return False
            return invoked
        if step == "research":
            self.action_save_research()
            return self._last_form_status.startswith("Saved research choice:")
        if step == "hosts":
            if self._selected_host_record() is None:
                self.action_create_host()
                if not self._last_form_status.startswith("Created host "):
                    return False
            else:
                self.action_save_host()
                if not self._last_form_status.startswith("Saved host "):
                    return False
            if self._selected_host_ids:
                self.action_save_host_order()
                return self._last_form_status.startswith("Saved ordered episode hosts ")
            return True
        if step == "episode":
            self.action_save_episode()
            return self._last_form_status.startswith("Saved episode settings ")
        if step == "plan":
            self.action_save_plan_segment()
            return self._last_form_status.startswith("Saved the selected segment ")
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
        self._schedule_form_baseline()

    def on_screen_resume(self) -> None:
        """A previously mounted wizard must reload production state when re-entered."""
        if not self.is_mounted:
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

    def action_continue(self) -> bool:
        if not super().action_continue():
            return False
        self._load_episode_form()
        self._refresh_plan()
        self._refresh_preflight()
        self._toggle()
        self._schedule_form_baseline()
        return True

    def action_back(self) -> bool:
        if not super().action_back():
            return False
        self._load_episode_form()
        self._refresh_plan()
        self._refresh_preflight()
        self._toggle()
        self._schedule_form_baseline()
        return True

    def on_select_changed(self, event: Select.Changed) -> None:
        super().on_select_changed(event)
        if event.select.id == "guided-plan-segment-picker":
            value = event.value
            if isinstance(value, str) and value.isdigit():
                self._selected_segment_ordinal = int(value)
                self._load_selected_segment()
        elif event.select.id == "guided-episode-duration":
            self._toggle_custom_duration()

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
        super().on_button_pressed(event)

    def action_toggle_episode_advanced(self) -> None:
        self._episode_advanced = not self._episode_advanced
        self._toggle()
        self.set_status(
            "Advanced episode options shown."
            if self._episode_advanced
            else "Advanced episode options hidden."
        )

    def action_save_episode(self) -> None:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            self.set_status("Choose and save episode hosts before configuring the episode.")
            return
        service = EpisodeConfigurationService(
            self.context.composition.database_for_project(project_id)
        )
        try:
            current = service.load_configuration(episode_id)
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
                target_duration_seconds=self._duration_seconds(),
                must_cover=self._csv("#guided-episode-must-cover"),
                avoid_topics=self._csv("#guided-episode-avoid"),
            )
            config.validate()
            service.edit(episode_id, config)
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            safe = sanitize_exception_message(exc)
            self.query_one("#guided-episode-validation", Static).update(
                f"Fix episode settings: {safe}"
            )
            self.set_status("Episode settings need attention before continuing.")
            return
        self.query_one("#guided-episode-validation", Static).update("")
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved episode settings through EpisodeConfigurationService.")

    def action_build_plan(self) -> None:
        self._run_plan_operation("build")

    def action_regenerate_plan(self) -> None:
        self._run_plan_operation("regenerate")

    def action_save_plan_segment(self) -> None:
        if self._plan is None or self.context.episode_id is None:
            self.set_status("Build a plan before editing a segment.")
            return
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
        except (IndexError, KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Plan edit failed.", exc)
            return
        self._render_plan()
        self._sync_text()
        self._remember_current_form()
        self.set_status("Saved the selected segment through EpisodePlannerService.")

    def action_regenerate_plan_segment(self) -> None:
        if self.context.episode_id is None:
            self.set_status("Build a plan before regenerating a segment.")
            return
        try:
            self._plan = self._planning_service().regenerate_segment(
                self.context.episode_id,
                self._selected_segment_ordinal,
            )
        except (IndexError, KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Segment regeneration failed.", exc)
            return
        self._render_plan()
        self._sync_text()
        self.set_status("Regenerated the selected segment through EpisodePlannerService.")

    def action_check_preflight(self) -> None:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            self.set_status("Complete episode setup before running preflight.")
            return
        try:
            self._preflight = GenerationStartService(self.context.composition).preflight(
                project_id,
                episode_id,
            )
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_error("Preflight failed.", exc)
            return
        self._render_preflight()
        self._sync_text()
        if self._preflight.ready:
            self.set_status("Preflight passed. Generation is ready to start.")
        else:
            self.set_status("Preflight found blockers. Use Fix First Blocker or Back.")

    def action_fix_preflight(self) -> None:
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
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
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
        except (KeyError, OSError, RuntimeError, ValueError) as exc:
            self.set_busy(False)
            self.set_error("Episode planning failed.", exc)
            return
        self.set_busy(False)
        self._render_plan()
        self._sync_text()
        self.set_status(
            "Regenerated the production episode plan."
            if operation == "regenerate"
            else "Built the production episode plan."
        )

    def _planning_service(self) -> EpisodePlannerService:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            raise ValueError("project and episode are required for planning")
        assignments, errors = self.context.composition.effective_model_role_assignments_for_episode(
            project_id,
            episode_id,
        )
        if errors:
            raise ValueError("invalid model-role configuration: " + "; ".join(errors))
        assignment = assignments.resolve(ModelRole.EPISODE_PLANNING)
        if assignment is None:
            raise ValueError("no provider/model assignment for episode_planning")
        return self.context.composition.configured_planning_service(
            project_id,
            assignment.provider,
            assignment.model,
        )

    def _load_episode_form(self) -> None:
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            return
        try:
            config = EpisodeConfigurationService(
                self.context.composition.database_for_project(project_id)
            ).load_configuration(episode_id)
        except (KeyError, ValueError):
            return
        self.query_one("#guided-episode-title", Input).value = config.title
        self.query_one("#guided-episode-focus", Input).value = config.focus
        self.query_one("#guided-episode-audience", Select).value = config.audience
        if config.technical_depth in {"accessible", "balanced", "deep"}:
            self.query_one("#guided-episode-depth", Select).value = config.technical_depth
        minutes = config.target_duration_seconds // 60
        if minutes in {10, 20, 30} and config.target_duration_seconds == minutes * 60:
            self.query_one("#guided-episode-duration", Select).value = str(minutes)
        else:
            self.query_one("#guided-episode-duration", Select).value = "custom"
            self.query_one("#guided-episode-custom-duration", Input).value = str(
                max(1, round(config.target_duration_seconds / 60))
            )
        self.query_one("#guided-episode-must-cover", Input).value = ", ".join(config.must_cover)
        self.query_one("#guided-episode-avoid", Input).value = ", ".join(config.avoid_topics)
        self._toggle_custom_duration()

    def _refresh_plan(self) -> None:
        summary = self.query_one("#guided-plan-summary", Static)
        if self.context.episode_id is None:
            self._plan = None
            summary.update("No plan loaded.")
            self._set_plan_controls()
            return
        try:
            self._plan = self._planning_service().load_plan(self.context.episode_id)
        except (KeyError, OSError, RuntimeError, ValueError):
            self._plan = None
        self._render_plan()

    def _render_plan(self) -> None:
        summary = self.query_one("#guided-plan-summary", Static)
        picker = self.query_one("#guided-plan-segment-picker", Select)
        if self._plan is None:
            summary.update("No plan loaded. Choose Build Plan.")
            picker.set_options([])
            self._set_plan_controls()
            return
        rows: list[str] = []
        options: list[tuple[str, str]] = []
        for ordinal, segment in enumerate(self._plan.segments):
            options.append((f"{ordinal + 1}. {segment.title}", str(ordinal)))
            rows.append(
                f"{ordinal + 1}. {segment.title} — {segment.target_duration_seconds}s — "
                f"{segment.purpose or 'No purpose supplied'}"
            )
        picker.set_options(options)
        if self._selected_segment_ordinal >= len(self._plan.segments):
            self._selected_segment_ordinal = 0
        picker.value = str(self._selected_segment_ordinal)
        summary.update(f"Plan total: {self._plan.target_duration_seconds}s\n" + "\n".join(rows))
        self._load_selected_segment()
        self._set_plan_controls()

    def _load_selected_segment(self) -> None:
        if self._plan is None or not self._plan.segments:
            return
        segment = self._plan.segments[self._selected_segment_ordinal]
        self.query_one("#guided-plan-title", Input).value = segment.title
        self.query_one("#guided-plan-purpose", Input).value = segment.purpose
        self.query_one("#guided-plan-duration", Input).value = str(segment.target_duration_seconds)

    def _refresh_preflight(self) -> None:
        if self.context.state.current_step != "preflight":
            return
        self.action_check_preflight()

    def _render_preflight(self) -> None:
        output = self.query_one("#guided-preflight-summary", Static)
        button = self.query_one("#guided-preflight-generate", Button)
        if self._preflight is None:
            output.update("Preflight has not run.")
            button.disabled = True
            return
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        plan_ready = False
        research_ready = False
        if project_id is not None and episode_id is not None:
            plan_ready = evaluate_episode_plan(
                self.context.composition.database_for_project(project_id),
                episode_id,
            ).usable
            research_ready = ResearchPolicyStore(
                self.context.composition.database_for_project(project_id)
            ).has_project_policy(project_id)
        codes = {issue.code for issue in self._preflight.blockers}
        rows = [
            (
                "Sources: Ready"
                if not codes & {"sources_missing", "sources_unindexed"}
                else "Sources: Needs attention"
            ),
            f"Research policy: {'Ready' if research_ready else 'Needs attention'}",
            f"Hosts: {'Ready' if 'hosts_missing' not in codes else 'Needs attention'}",
            f"Plan: {'Ready' if plan_ready else 'Needs attention'}",
            (
                "Models/providers: Ready"
                if not codes & {"llm_assignment", "llm_unhealthy"}
                else "Models/providers: Needs attention"
            ),
            (
                "Speech/voices: Ready"
                if not codes & {"tts_assignment", "tts_unhealthy", "tts_format_unsupported"}
                else "Speech/voices: Needs attention"
            ),
            f"FFmpeg: {'Ready' if 'ffmpeg_unavailable' not in codes else 'Needs attention'}",
            (
                "Network policy: Ready"
                if not codes & {"local_only_violation", "source_content_remote"}
                else "Network policy: Needs attention"
            ),
        ]
        if self._preflight.issues:
            rows.append("Details:")
            rows.extend(
                f"- {'Blocker' if issue.fatal else 'Optional'} [{issue.code}]: {issue.message}"
                for issue in self._preflight.issues
            )
        else:
            rows.append("No preflight blockers or warnings.")
        output.update("\n".join(rows))
        button.disabled = not self._preflight.ready

    def _duration_seconds(self) -> int:
        value = self._select_value("#guided-episode-duration")
        if value is None:
            raise ValueError("choose an episode duration")
        if value == "custom":
            raw = self.query_one("#guided-episode-custom-duration", Input).value.strip()
            try:
                minutes = int(raw)
            except ValueError as exc:
                raise ValueError("custom duration must be a whole number of minutes") from exc
            if minutes <= 0:
                raise ValueError("custom duration must be positive")
            return minutes * 60
        return int(value) * 60

    def _csv(self, selector: str) -> tuple[str, ...]:
        return tuple(
            item.strip()
            for item in self.query_one(selector, Input).value.split(",")
            if item.strip()
        )

    def _select_value(self, selector: str) -> str | None:
        value = self.query_one(selector, Select).value
        return value if isinstance(value, str) and value else None

    def _toggle_custom_duration(self) -> None:
        custom = self._select_value("#guided-episode-duration") == "custom"
        self.query_one("#guided-episode-custom-duration", Input).display = custom

    def _set_plan_controls(self) -> None:
        has_plan = self._plan is not None
        for selector in (
            "#guided-plan-segment-picker",
            "#guided-plan-title",
            "#guided-plan-purpose",
            "#guided-plan-duration",
            "#guided-plan-save-segment",
            "#guided-plan-regenerate-segment",
        ):
            self.query_one(selector).disabled = not has_plan

    @staticmethod
    def _advanced_route_for_issue(code: str) -> str | None:
        if code == "ffmpeg_unavailable":
            return "setup"
        if code in {
            "llm_assignment",
            "llm_unhealthy",
            "tts_unhealthy",
            "tts_format_unsupported",
            "local_only_violation",
            "source_content_remote",
        }:
            return "providers"
        return None

    @staticmethod
    def _route_for_issue(code: str) -> str | None:
        if code in {"sources_missing", "sources_unindexed"}:
            return "sources"
        if code in {"hosts_missing", "tts_assignment"}:
            return "hosts"
        if code in {"episode_missing", "duration_invalid"}:
            return "episode"
        if code.startswith("plan"):
            return "plan"
        return None

    def _toggle(self) -> None:
        super()._toggle()
        step = self.context.state.current_step
        for selector in (
            "#guided-episode-title",
            "#guided-episode-focus",
            "#guided-episode-duration",
            "#guided-episode-custom-duration",
            "#guided-episode-audience",
            "#guided-episode-advanced",
            "#guided-episode-save",
        ):
            self.query_one(selector).display = step == "episode"
        for selector in (
            "#guided-episode-depth",
            "#guided-episode-must-cover",
            "#guided-episode-avoid",
        ):
            self.query_one(selector).display = step == "episode" and self._episode_advanced
        self._toggle_custom_duration()
        if step != "episode":
            self.query_one("#guided-episode-custom-duration", Input).display = False

        for selector in (
            "#guided-plan-summary",
            "#guided-plan-segment-picker",
            "#guided-plan-title",
            "#guided-plan-purpose",
            "#guided-plan-duration",
            "#guided-plan-build",
            "#guided-plan-save-segment",
            "#guided-plan-regenerate-segment",
            "#guided-plan-regenerate",
        ):
            self.query_one(selector).display = step == "plan"

        for selector in (
            "#guided-preflight-summary",
            "#guided-preflight-check",
            "#guided-preflight-fix",
            "#guided-preflight-generate",
        ):
            self.query_one(selector).display = step == "preflight"
