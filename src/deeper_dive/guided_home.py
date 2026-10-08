"""Goal-first Home actions and durable summaries for the guided Textual entry point."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Button, Static

from deeper_dive.guided_readiness import first_run_readiness
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.tui import DeeperDiveApp


def _readiness_label(app: DeeperDiveApp) -> str:
    context = WizardContext(
        app.composition,
        WizardState(WizardKind.FIRST_RUN, "welcome"),
    )
    readiness = first_run_readiness(context)
    if not readiness.setup_ready:
        return "Setup needs attention — open Setup to review providers and defaults."
    if not readiness.audio_ready:
        return "Setup ready for text workflows; audio requires a configured speech provider."
    return "Setup ready — model, roles, speech, and defaults are configured."


def _recent_episode_lines(app: DeeperDiveApp) -> str:
    """Derive Home episode summaries from the normal project repositories."""
    entries: list[tuple[str, str]] = []
    for project in app.service.list_project_summaries():
        for episode in app.service.hosts(project.id).list_episodes(project.id):
            run = app.service.runs(project.id).latest_for_episode(episode.id)
            state = run.state if run is not None else episode.state
            entries.append(
                (
                    episode.modified_at,
                    f"{episode.title} — {project.name} ({state})",
                )
            )
    if not entries:
        return "Recent episodes: None yet. Start a New Deep Dive."
    entries.sort(key=lambda item: item[0], reverse=True)
    return "Recent episodes:\n" + "\n".join(
        f"  • {line}" for _, line in entries[:5]
    )


def refresh_goal_home(app: DeeperDiveApp) -> None:
    """Refresh derived Home information whenever the user returns."""
    home = app.get_screen("home")
    home.query_one("#home-readiness", Static).update(Text(_readiness_label(app)))
    home.query_one("#home-recent-episodes", Static).update(
        Text(_recent_episode_lines(app))
    )
    projects = sorted(
        app.service.list_project_summaries(),
        key=lambda item: item.modified_at,
        reverse=True,
    )
    recent = ", ".join(project.name for project in projects[:5]) or "None yet"
    home.query_one("#home-recent-projects", Static).update(
        Text(f"Recent projects: {recent}")
    )
    # Retain existing project lifecycle operations, with up-to-date selection.
    home.refresh_projects()  # type: ignore[attr-defined]


def add_new_deep_dive_action(app: DeeperDiveApp) -> None:
    """Promote user goals without removing any advanced or project operations."""
    home = app.get_screen("home")
    primary = home.query_one("#global-nav")
    advanced = home.query_one("#project-nav")

    # Reuse the existing buttons so their event handlers and focus order stay stable.
    for button, (label, destination) in zip(
        primary.query(Button),
        (
            ("Home", "home"),
            ("New Deep Dive", "new"),
            ("Projects", "projects"),
            ("Library", "library"),
        ),
        strict=True,
    ):
        button.label = label
        button.name = destination

    for button, (label, destination) in zip(
        advanced.query(Button),
        (
            ("Sources", "sources"),
            ("Research", "research"),
            ("Hosts", "hosts"),
            ("Providers", "providers"),
            ("Settings", "settings"),
            ("Help", "help"),
        ),
        strict=True,
    ):
        button.label = label
        button.name = destination

    # Existing episode and preflight screens remain reachable for expert users.
    advanced.mount(
        Button("Episode", name="episode", id="guided-advanced-episode"),
        Button("Generate", name="generate", id="guided-advanced-generate"),
    )

    home.query_one("#screen-title", Static).update("Home")
    home.query_one("#screen-description", Static).update(
        "Create a Deep Dive, open a project, or review episodes. "
        "Advanced tools remain available below."
    )
    content = home.query_one("#content")
    content.mount(
        Button("New Deep Dive", name="new", id="action-new-deep-dive"),
        before="#new-project-name",
    )
    content.mount(
        Static(Text(_readiness_label(app)), id="home-readiness"),
        Static(Text("Recent projects: None yet"), id="home-recent-projects"),
        Static(Text(_recent_episode_lines(app)), id="home-recent-episodes"),
        before="#new-project-name",
    )
