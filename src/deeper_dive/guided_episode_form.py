"""Plan service, episode form, plan rendering and preflight helpers for the episode wizard."""

from __future__ import annotations

import sqlite3
from typing import Any

from textual.widgets import Button, Input, Select, Static

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_planner import EpisodePlan, EpisodePlannerService
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.guided_host_wizard import GuidedHostWizard
from deeper_dive.guided_workflow import CompletionProbe, WizardContext
from deeper_dive.model_roles import ModelRole
from deeper_dive.plan_validity import evaluate_episode_plan
from deeper_dive.preflight import PreflightReport
from deeper_dive.research_policy import ResearchPolicyStore

AUDIENCE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("General audience", "general"),
    ("Technical audience", "technical"),
    ("Expert audience", "expert"),
)


class _UnavailablePlanGenerator:
    """Generator for read-only planner use; generation is never configured here."""

    def generate_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        _ = request
        raise RuntimeError("episode plan generation is not configured")


class EpisodeFormHelpers(GuidedHostWizard):
    """Plan service, episode form, plan rendering and preflight helpers for the episode wizard."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe)
        self._plan: EpisodePlan | None = None
        self._selected_segment_ordinal = 0
        self._loaded_segment_ordinal: int | None = None
        self._preflight: PreflightReport | None = None
        self._episode_advanced = False
        # Guard against another writer changing durable settings while this form is open.
        self._loaded_episode_id: str | None = None
        self._loaded_episode_config: EpisodeConfiguration | None = None
        self._loaded_episode_revision: str | None = None

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

    def _show_audience(self, audience: str) -> None:
        """Show a stored audience, adding a "Custom" option for free text.

        The CLI and the legacy Episode Setup screen accept any audience text. The
        guided Select only knows the presets, so an unknown stored value becomes an
        extra option; a no-op Save then keeps the durable value unchanged.
        """

        select = self.query_one("#guided-episode-audience", Select)
        options = list(AUDIENCE_OPTIONS)
        if audience not in {value for _label, value in options}:
            options.append((f"Custom: {audience}", audience))
        with select.prevent(Select.Changed):
            select.set_options(options)
            select.value = audience

    def _load_episode_form(self) -> None:
        self._loaded_episode_id = None
        self._loaded_episode_config = None
        self._loaded_episode_revision = None
        project_id = self.context.project_id
        episode_id = self.context.episode_id
        if project_id is None or episode_id is None:
            return
        try:
            config, revision = EpisodeConfigurationService(
                self.context.composition.database_for_project(project_id)
            ).load_with_revision(episode_id)
        except (KeyError, ValueError):
            return
        self._loaded_episode_id = episode_id
        self._loaded_episode_config = config
        self._loaded_episode_revision = revision
        self.query_one("#guided-episode-title", Input).value = config.title
        self.query_one("#guided-episode-focus", Input).value = config.focus
        self._show_audience(config.audience)
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
        if (
            self.context.state.current_step == "plan"
            and self._plan is not None
            and self._current_form_dirty()
        ):
            self.set_status(
                "Unsaved plan segment changes remain; save or discard before reloading."
            )
            return
        summary = self.query_one("#guided-plan-summary", Static)
        if self.context.episode_id is None:
            self._plan = None
            summary.update("No plan loaded.")
            self._set_plan_controls()
            return
        project_id = self.context.project_id
        try:
            if project_id is None:
                raise KeyError(self.context.episode_id)
            # Reading a stored plan needs no model: a reader whose generator is
            # never called keeps an existing plan visible when roles are unusable.
            reader = self.context.composition.planning_service(
                project_id, _UnavailablePlanGenerator()
            )
            self._plan = reader.load_plan(self.context.episode_id)
        except KeyError:
            self._plan = None  # no plan yet is the normal state before Build Plan
        except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self._plan = None
            self.set_status(
                "The saved plan could not be loaded: " + sanitize_exception_message(exc)
            )
        self._render_plan()
        if self.context.state.current_step == "plan":
            self._remember_current_form()

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
        self._loaded_segment_ordinal = self._selected_segment_ordinal
        self.query_one("#guided-plan-title", Input).value = segment.title
        self.query_one("#guided-plan-purpose", Input).value = segment.purpose
        self.query_one("#guided-plan-duration", Input).value = str(segment.target_duration_seconds)

    def _refresh_preflight(self) -> None:
        if self.context.state.current_step != "preflight":
            return
        self.action_check_preflight()

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
        except (KeyError, OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
            self.set_error("Preflight failed.", exc)
            return
        self._render_preflight()
        self._sync_text()
        if self._preflight.ready:
            self.set_status("Preflight passed. Generation is ready to start.")
        else:
            self.set_status("Preflight found blockers. Use Fix First Blocker or Back.")

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

    def _duration_seconds(self, persisted_seconds: int | None = None) -> int:
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
            # The guided form displays whole minutes, but imported/CLI episodes
            # can retain an exact duration in seconds. A no-op guided save must
            # not round that value and invalidate an otherwise unchanged plan.
            if (
                persisted_seconds is not None
                and persisted_seconds % 60
                and minutes == max(1, round(persisted_seconds / 60))
            ):
                return persisted_seconds
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
