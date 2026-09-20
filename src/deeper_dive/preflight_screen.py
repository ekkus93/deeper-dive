"""Generation preflight Textual screen."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.hosts import HostProfile
from deeper_dive.model_roles import (
    ModelRole,
    ModelRoleAssignments,
    effective_model_role_assignments,
)
from deeper_dive.preflight import (
    PreflightEstimate,
    PreflightIssue,
    PreflightReport,
    PreflightService,
)
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodeRecord,
    HostEpisodeRepository,
    HostProfileRecord,
)
from deeper_dive.tts import TTSProviderRegistry
from deeper_dive.user_config import ProviderConfig


@dataclass(frozen=True, slots=True)
class PreflightPresentation:
    """Pre-rendered preflight state for the Generate screen."""

    project_name: str
    source_count: int
    indexed_source_count: int
    host_count: int
    target_minutes: float
    llm_rows: tuple[str, ...]
    tts_rows: tuple[str, ...]
    report: PreflightReport


@dataclass(slots=True)
class PreflightController:
    """Build generation preflight reports from current TUI application state."""

    ffmpeg_executable: Path | None = None
    default_target_minutes: float = 20.0

    def build(self, app: PreflightApp) -> PreflightPresentation:
        project_id = app.current_project_id
        if project_id is None:
            report = PreflightReport(
                (PreflightIssue("project_missing", "open a project before generation"),),
                PreflightEstimate(self.default_target_minutes, 0, 0, None),
            )
            return PreflightPresentation(
                project_name="none",
                source_count=0,
                indexed_source_count=0,
                host_count=0,
                target_minutes=self.default_target_minutes,
                llm_rows=("No project open.",),
                tts_rows=("No project open.",),
                report=report,
            )

        sources = [source for source in app.service.list_sources(project_id) if source.included]
        indexed_source_count = sum(
            1 for source in sources if app.service.list_source_chunks(project_id, source.id)
        )
        host_repository = app.service.hosts(project_id)
        episode = self._selected_episode(host_repository, project_id, app.current_episode_id)
        target_minutes = self._target_minutes(episode)
        host_records = self._selected_host_records(host_repository, project_id, episode)
        hosts = tuple(HostProfile.from_record(host) for host in host_records)
        config = app.provider_controller.config()
        episode_overrides = self._episode_model_overrides(app, project_id, episode)
        assignments, assignment_issues = self._assignments(
            config.defaults, episode_overrides
        )

        tts_registry = TTSProviderRegistry()
        for provider in app.provider_controller.tts_providers.values():
            tts_registry.register(provider)
        report = PreflightService(
            app.provider_controller.llm_registry,
            tts_registry,
        ).check(
            assignments=assignments,
            hosts=hosts,
            source_count=len(sources),
            indexed_source_count=indexed_source_count,
            target_minutes=target_minutes,
            ffmpeg_executable=self.ffmpeg_executable,
            local_provider_ids=self._local_provider_ids(config.providers, config.defaults),
            local_only=self._local_only(config.defaults),
        )
        if assignment_issues:
            report = PreflightReport(
                (*assignment_issues, *report.issues),
                report.estimate,
                report.routes,
            )

        return PreflightPresentation(
            project_name=app.current_project_name or project_id,
            source_count=len(sources),
            indexed_source_count=indexed_source_count,
            host_count=len(hosts),
            target_minutes=target_minutes,
            llm_rows=self._llm_rows(assignments),
            tts_rows=self._tts_rows(hosts),
            report=report,
        )

    def _selected_episode(
        self,
        repository: HostEpisodeRepository,
        project_id: str,
        selected_episode_id: str | None,
    ) -> EpisodeRecord | None:
        if selected_episode_id is not None:
            episode = repository.get_episode(selected_episode_id)
            if episode is not None and episode.project_id == project_id:
                return episode
        episodes = repository.list_episodes(project_id)
        return episodes[-1] if episodes else None

    def _target_minutes(self, episode: EpisodeRecord | None) -> float:
        if episode is not None and episode.target_duration_seconds > 0:
            return episode.target_duration_seconds / 60
        return self.default_target_minutes

    @staticmethod
    def _selected_host_records(
        repository: HostEpisodeRepository,
        project_id: str,
        episode: EpisodeRecord | None,
    ) -> tuple[HostProfileRecord, ...]:
        hosts = repository.list_hosts(project_id)
        if episode is None:
            return tuple(hosts)
        host_ids = repository.list_episode_host_ids(episode.id)
        by_id = {host.id: host for host in hosts}
        return tuple(by_id[host_id] for host_id in host_ids if host_id in by_id)

    @staticmethod
    def _episode_model_overrides(
        app: PreflightApp,
        project_id: str,
        episode: EpisodeRecord | None,
    ) -> dict[str, dict[str, str]]:
        if episode is None:
            return {}
        database = Database(app.service.workspaces.project_root(project_id) / "project.db")
        try:
            config = EpisodeConfigurationService(database).load_configuration(episode.id)
        except KeyError:
            return {}
        return {role: dict(assignment) for role, assignment in config.model_overrides.items()}

    @staticmethod
    def _assignments(
        defaults: dict[str, str],
        episode_overrides: dict[str, dict[str, str]] | None = None,
    ) -> tuple[ModelRoleAssignments, tuple[PreflightIssue, ...]]:
        assignments, errors = effective_model_role_assignments(
            user_defaults=defaults,
            episode_overrides=episode_overrides or {},
        )
        issues = tuple(PreflightIssue("llm_assignment", error) for error in errors)
        return assignments, issues

    @staticmethod
    def _local_provider_ids(
        providers: dict[str, ProviderConfig], defaults: dict[str, str]
    ) -> frozenset[str]:
        local_ids = {
            value.strip()
            for value in defaults.get("local_provider_ids", "").split(",")
            if value.strip()
        }
        local_types = {"fake", "fake-tts", "kitten", "llama-server", "local", "ollama"}
        for name, provider in providers.items():
            if provider.provider_type in local_types:
                local_ids.add(name)
        return frozenset(local_ids)

    @staticmethod
    def _local_only(defaults: dict[str, str]) -> bool:
        return defaults.get("local_only", "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _llm_rows(assignments: ModelRoleAssignments) -> tuple[str, ...]:
        rows: list[str] = []
        for role in ModelRole:
            assignment = assignments.resolve(role)
            if assignment is None:
                rows.append(f"{role.value}: unassigned")
            else:
                rows.append(f"{role.value}: {assignment.provider}:{assignment.model}")
        return tuple(rows)

    @staticmethod
    def _tts_rows(hosts: tuple[HostProfile, ...]) -> tuple[str, ...]:
        if not hosts:
            return ("No hosts configured.",)
        return tuple(
            f"{host.display_name}: {host.tts_provider or 'unassigned'} / "
            f"{host.tts_voice or 'unassigned'}"
            for host in hosts
        )


class PreflightApp(Protocol):
    service: DeeperDiveService
    provider_controller: ProviderController
    preflight_controller: PreflightController
    current_project_id: str | None
    current_project_name: str | None
    current_episode_id: str | None

    def action_navigate(self, destination: str) -> None: ...


class PreflightScreen(Screen[None]):
    """Preflight review and generation gate screen."""

    def __init__(self) -> None:
        super().__init__(id="screen-generate")

    @property
    def _app(self) -> PreflightApp:
        return cast(PreflightApp, self.app)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in ("home", "providers", "settings", "help"):
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with Horizontal(id="project-nav"):
            for key in ("sources", "research", "hosts", "episode", "generate", "library"):
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with VerticalScroll(id="content"):
            yield Label("Generation Preflight", id="screen-title")
            yield Static(
                "Review generation readiness before starting expensive provider calls.",
                id="screen-description",
            )
            yield Static("", id="preflight-summary")
            yield Static("", id="llm-preflight")
            yield Static("", id="tts-preflight")
            yield Static("", id="routing-preflight")
            yield Static("", id="ffmpeg-preflight")
            yield Static("", id="preflight-issues")
            yield Button("Generate", id="action-generate", name="start-generation")
            yield Button("Cancel", id="action-cancel", name="cancel-generation")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_preflight()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        if name == "start-generation":
            self.action_generate()
        elif name == "cancel-generation":
            self.action_cancel()
        elif name:
            self._app.action_navigate(name)

    def action_generate(self) -> None:
        presentation = self._app.preflight_controller.build(self._app)
        if presentation.report.ready:
            self._status("Preflight passed; generation start is ready")
            return
        first = presentation.report.blockers[0]
        self._status(f"Generation blocked: {first.message}")

    def action_cancel(self) -> None:
        self._app.action_navigate("episode")

    def refresh_preflight(self) -> None:
        presentation = self._app.preflight_controller.build(self._app)
        self.query_one("#preflight-summary", Static).update(self._summary_text(presentation))
        self.query_one("#llm-preflight", Static).update(
            "LLM role assignments / health:\n" + "\n".join(presentation.llm_rows)
        )
        self.query_one("#tts-preflight", Static).update(
            "TTS host assignments / health:\n" + "\n".join(presentation.tts_rows)
        )
        self.query_one("#routing-preflight", Static).update(
            self._routing_text(presentation.report)
        )
        self.query_one("#ffmpeg-preflight", Static).update(self._ffmpeg_text(presentation.report))
        self.query_one("#preflight-issues", Static).update(self._issue_text(presentation.report))
        blocker_count = len(presentation.report.blockers)
        if blocker_count:
            self._status(f"Blocked: {blocker_count} blocker(s)")
        else:
            self._status("Ready to generate")

    def _summary_text(self, presentation: PreflightPresentation) -> str:
        estimate = presentation.report.estimate
        cost = (
            f"${estimate.estimated_cloud_cost_usd:.4f} estimated"
            if estimate.estimated_cloud_cost_usd is not None
            else "not configured"
        )
        return "\n".join(
            (
                f"Project: {presentation.project_name}",
                f"Sources: {presentation.source_count} included / "
                f"{presentation.indexed_source_count} indexed",
                f"Hosts: {presentation.host_count}",
                f"Expected duration: {presentation.target_minutes:.1f} minutes",
                f"Estimate: {estimate.estimated_words} words / "
                f"{estimate.estimated_output_tokens} output tokens",
                f"Cloud cost estimate: {cost}",
            )
        )

    @staticmethod
    def _routing_text(report: PreflightReport) -> str:
        if not report.routes:
            return "Content routing:\nNo provider routes resolved."
        rows = ["Content routing:"]
        for route in report.routes:
            locality = "local" if route.local else "remote"
            model = f":{route.model}" if route.model else ""
            rows.append(
                f"{route.stage}: {route.provider}{model} | {locality} | {route.content}"
            )
        return "\n".join(rows)

    @staticmethod
    def _ffmpeg_text(report: PreflightReport) -> str:
        issue = next(
            (item for item in report.issues if item.code == "ffmpeg_unavailable"),
            None,
        )
        if issue is None:
            return "FFmpeg: available"
        return f"FFmpeg: unavailable - {issue.message}"

    @staticmethod
    def _issue_text(report: PreflightReport) -> str:
        if report.ready and not report.warnings:
            return "Blockers: none\nWarnings: none"
        lines: list[str] = ["Blockers:"]
        if report.blockers:
            lines.extend(f"! {issue.message} [{issue.code}]" for issue in report.blockers)
        else:
            lines.append("none")
        lines.append("Warnings:")
        if report.warnings:
            lines.extend(f"- {issue.message} [{issue.code}]" for issue in report.warnings)
        else:
            lines.append("none")
        return "\n".join(lines)

    def _status(self, message: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {message}")
