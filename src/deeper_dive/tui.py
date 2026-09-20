"""Textual application shell for Deeper Dive."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Static

from deeper_dive.application.service import DeeperDiveService, ProjectSummary, SourceImportSummary
from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.episode_plan_screen import EpisodePlanController, EpisodePlanScreen
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.generation_monitor import GenerationMonitorController, GenerationMonitorScreen
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.provider_tui import ProviderController
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.research_screen import ResearchController, ResearchScreen
from deeper_dive.storage.repositories import SourceRecord

GLOBAL_SCREENS = ("home", "providers", "settings", "help")
PROJECT_SCREENS = ("sources", "research", "hosts", "episode", "generate", "library")


def _nav() -> ComposeResult:
    with Horizontal(id="global-nav"):
        for key in GLOBAL_SCREENS:
            yield Button(key.title(), id=f"nav-{key}", name=key)
    with Horizontal(id="project-nav"):
        for key in PROJECT_SCREENS:
            yield Button(key.title(), id=f"nav-{key}", name=key)


class NavigationMixin:
    """Shared button navigation for shell screens."""

    @property
    def _navigation_app(self) -> DeeperDiveApp:
        return cast(DeeperDiveApp, cast(Screen[None], self).app)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        destination = event.button.name
        if destination:
            self._navigation_app.action_navigate(destination)


class HomeProjectsScreen(NavigationMixin, Screen[None]):
    """Project list and project lifecycle workflow."""

    BINDINGS = [
        Binding("ctrl+n", "create_project", "New project"),
        Binding("ctrl+o", "open_selected", "Open project"),
