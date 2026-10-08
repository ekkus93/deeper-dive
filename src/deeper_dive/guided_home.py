"""Goal-first action on the existing project Home screen."""

from textual.app import App
from textual.widgets import Button


def add_new_deep_dive_action(app: App[None]) -> None:
    home = app.get_screen("home")
    home.query_one("#content").mount(
        Button("New Deep Dive", name="new", id="action-new-deep-dive"),
        before="#new-project-name",
    )
