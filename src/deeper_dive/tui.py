"""Textual application shell for Deeper Dive."""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static

GLOBAL_SCREENS = ("home", "providers", "settings", "help")
PROJECT_SCREENS = ("sources", "research", "hosts", "episode", "generate", "library")


class ShellScreen(Screen[None]):
    """Simple named destination used until feature-specific screens replace the shell."""

    def __init__(self, key: str, title: str, description: str) -> None:
        super().__init__(id=f"screen-{key}")
        self.key = key
        self.title = title
        self.description = description

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="global-nav"):
            for key in GLOBAL_SCREENS:
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with Horizontal(id="project-nav"):
            for key in PROJECT_SCREENS:
                yield Button(key.title(), id=f"nav-{key}", name=key)
        with VerticalScroll(id="content"):
            yield Label(self.title, id="screen-title")
            yield Static(self.description, id="screen-description")
            yield Static("Status: Ready", id="screen-status")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        destination = event.button.name
        if destination and destination != self.key:
            self.app.push_screen(destination)


class DeeperDiveApp(App[None]):
    """Responsive keyboard-first application shell."""

    TITLE = "Deeper Dive"
    SUB_TITLE = "Evidence-grounded audio conversations"
    ENABLE_COMMAND_PALETTE = True
    CSS = """
    Screen { layout: vertical; }
    #global-nav, #project-nav { height: auto; padding: 0 1; }
    #global-nav Button, #project-nav Button { min-width: 10; margin: 0 1 0 0; }
    #content { padding: 1 2; }
    #screen-title { text-style: bold; margin-bottom: 1; }
    #screen-status { margin-top: 1; }
    @media (max-width: 79) {
        #global-nav, #project-nav { height: auto; overflow-x: auto; }
        #global-nav Button, #project-nav Button { min-width: 8; }
        #content { padding: 1; }
    }
    """
    BINDINGS = [
        Binding("h", "navigate('home')", "Home"),
        Binding("p", "navigate('providers')", "Providers"),
        Binding("s", "navigate('settings')", "Settings"),
        Binding("?", "navigate('help')", "Help"),
        Binding("1", "navigate('sources')", "Sources"),
        Binding("2", "navigate('research')", "Research"),
        Binding("3", "navigate('hosts')", "Hosts"),
        Binding("4", "navigate('episode')", "Episode"),
        Binding("5", "navigate('generate')", "Generate"),
        Binding("6", "navigate('library')", "Library"),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("q", "quit", "Quit"),
    ]
    SCREENS = {
        "home": lambda: ShellScreen("home", "Projects", "Create or open a Deeper Dive project."),
        "providers": lambda: ShellScreen(
            "providers", "Providers", "Configure language-model and speech providers."
        ),
        "settings": lambda: ShellScreen("settings", "Settings", "Application preferences."),
        "help": lambda: ShellScreen(
            "help", "Help", "Use the footer, keyboard shortcuts, or command palette to navigate."
        ),
        "sources": lambda: ShellScreen("sources", "Sources", "Primary and supplemental sources."),
        "research": lambda: ShellScreen("research", "Research", "Research gaps and web evidence."),
        "hosts": lambda: ShellScreen("hosts", "Hosts", "Conversation host profiles."),
        "episode": lambda: ShellScreen("episode", "Episode", "Episode configuration and plan."),
        "generate": lambda: ShellScreen("generate", "Generate", "Preflight and generation status."),
        "library": lambda: ShellScreen("library", "Library", "Generated episodes and exports."),
    }

    def on_mount(self) -> None:
        self.push_screen("home")

    def action_navigate(self, destination: str) -> None:
        if destination in self.SCREENS:
            self.push_screen(destination)


def main() -> None:
    """Run the Textual interface."""

    DeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
