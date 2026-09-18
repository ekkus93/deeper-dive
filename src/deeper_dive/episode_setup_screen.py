"""Episode setup screen for configuring draft episodes before generation."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.model_roles import (
    ModelAssignment,
    ModelRole,
    ModelRoleAssignments,
    preflight_model_roles,
)
from deeper_dive.storage.database import Database

if TYPE_CHECKING:
    from deeper_dive.tui import DeeperDiveApp


class EpisodeSetupScreen(Screen[None]):
    """Configure episode title, focus, audience, hosts, and planning preflight."""

    def __init__(self) -> None:
        super().__init__(id="screen-episode")
        self.current_episode_id: str | None = None

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
            yield Label("Episode Setup", id="screen-title")
            yield Static("Configure an episode before planning dialogue or TTS.", id="screen-description")
            yield Input(placeholder="Title", id="episode-title")
            yield Input(placeholder="Focus / central question", id="episode-focus")
            yield Input(value="general", placeholder="Audience", id="episode-audience")
            yield Input(value="balanced", placeholder="Technical depth", id="episode-depth")
            yield Input(value="1800", placeholder="Duration in seconds", id="episode-duration")
            yield Input(value="discussion", placeholder="Style", id="episode-style")
            yield Input(placeholder="Host IDs in order, comma separated; blank = all hosts", id="episode-hosts")
            yield Static("Host selection: none", id="host-summary")
            yield Input(placeholder="Must-cover topics, comma separated", id="episode-must-cover")
            yield Input(placeholder="Avoid topics, comma separated", id="episode-avoid")
            yield Input(value="project-default", placeholder="Research policy", id="episode-research-policy")
            yield Input(value="grounded", placeholder="Citation behavior", id="episode-citation-behavior")
            yield Button("Build Plan", id="action-build-plan", name="build-plan")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_summary()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        name = event.button.name or ""
        if name == "build-plan":
            self.action_build_plan()
        elif name:
            self._app.action_navigate(name)

    def action_build_plan(self) -> None:
        project_id = self._app.current_project_id
        if project_id is None:
            self._status("Open a project before configuring an episode")
            return
        try:
            config = self._configuration(project_id)
        except ValueError as exc:
            self._status(str(exc))
            return
        blocker = self._planning_role_blocker()
        if blocker is not None:
            self._status(blocker)
            return
        service = self._configuration_service(project_id)
        if self.current_episode_id is None:
            episode = service.create(project_id, config)
            self.current_episode_id = episode.id
            self._status(f"Episode setup saved: {episode.title}")
        else:
            episode = service.edit(self.current_episode_id, config)
            self._status(f"Episode setup updated: {episode.title}")
        self.refresh_summary()

    def refresh_summary(self) -> None:
        project_id = self._app.current_project_id
        if project_id is None:
            self.query_one("#host-summary", Static).update("Host selection: no project open")
            return
        hosts = self._app.service.hosts(project_id).list_hosts(project_id)
        if not hosts:
            self.query_one("#host-summary", Static).update("Host selection: no hosts configured")
            return
        selected = self._host_ids(project_id)
        rows = [f"{index + 1}. {host.display_name} [{host.id}]" for index, host in enumerate(hosts)]
        self.query_one("#host-summary", Static).update(
            "Host selection/order:\n" + "\n".join(rows) + f"\nSelected: {', '.join(selected)}"
        )

    def _configuration(self, project_id: str) -> EpisodeConfiguration:
        title = self.query_one("#episode-title", Input).value.strip()
        duration_text = self.query_one("#episode-duration", Input).value.strip()
        try:
            duration = int(duration_text)
        except ValueError as exc:
            raise ValueError("duration must be an integer number of seconds") from exc
        host_ids = self._host_ids(project_id)
        if not host_ids:
            raise ValueError("Add at least one host before planning an episode")
        return EpisodeConfiguration(
            title=title,
            focus=self.query_one("#episode-focus", Input).value.strip(),
            audience=self.query_one("#episode-audience", Input).value.strip() or "general",
            technical_depth=self.query_one("#episode-depth", Input).value.strip() or "balanced",
            target_duration_seconds=duration,
            style=self.query_one("#episode-style", Input).value.strip() or "discussion",
            host_ids=host_ids,
            must_cover=self._csv("#episode-must-cover"),
            avoid_topics=self._csv("#episode-avoid"),
            research_overrides={
                "policy": self.query_one("#episode-research-policy", Input).value.strip(),
                "citation_behavior": self.query_one("#episode-citation-behavior", Input).value.strip(),
            },
        )

    def _host_ids(self, project_id: str) -> tuple[str, ...]:
        available = self._app.service.hosts(project_id).list_hosts(project_id)
        available_ids = {host.id for host in available}
        configured = self._csv("#episode-hosts")
        selected = configured or tuple(host.id for host in available)
        missing = [host_id for host_id in selected if host_id not in available_ids]
        if missing:
            raise ValueError(f"Unknown episode host ID: {missing[0]}")
        return selected

    def _planning_role_blocker(self) -> str | None:
        config = self._app.provider_controller.config()
        default = config.defaults.get(ModelRole.EPISODE_PLANNING.value)
        if not default:
            return "Configure an episode_planning provider/model before building a plan"
        try:
            provider, model = default.split(":", 1)
            assignment = ModelAssignment(provider, model)
        except ValueError:
            return "Default episode_planning role must use provider:model"
        preflight = preflight_model_roles(
            ModelRoleAssignments(user={ModelRole.EPISODE_PLANNING: assignment}),
            self._app.provider_controller.llm_registry,
            required_roles=(ModelRole.EPISODE_PLANNING,),
        )
        if preflight.ready:
            return None
        return preflight.blockers[0].message

    def _configuration_service(self, project_id: str) -> EpisodeConfigurationService:
        database = Database(self._app.service.workspaces.project_root(project_id) / "project.db")
        return EpisodeConfigurationService(database)

    def _csv(self, selector: str) -> tuple[str, ...]:
        raw = self.query_one(selector, Input).value
        return tuple(value.strip() for value in raw.split(",") if value.strip())

    def _status(self, value: str) -> None:
        self.query_one("#screen-status", Static).update(f"Status: {value}")
