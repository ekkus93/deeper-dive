"""Production entry point for the guided Textual startup workflow."""

from __future__ import annotations

from textual.binding import Binding

from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.guided_home import add_new_deep_dive_action
from deeper_dive.guided_readiness import ProductionWizardCompletion, first_run_readiness
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.tui import DeeperDiveApp


class GuidedDeeperDiveApp(DeeperDiveApp):
    """Route first-run and New Deep Dive through the shared production context."""

    BINDINGS = [
        *DeeperDiveApp.BINDINGS,
        Binding("ctrl+g", "navigate('new')", "New Deep Dive"),
    ]

    def on_ready(self) -> None:
        add_new_deep_dive_action(self)

        setup_context = WizardContext(
            self.composition,
            WizardState(WizardKind.FIRST_RUN, "welcome"),
        )
        self.install_screen(
            GuidedFirstRunWizard(
                setup_context,
                ProductionWizardCompletion(setup_context),
            ),
            name="setup",
        )

        new_context = WizardContext(
            self.composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "project"),
        )
        self.install_screen(
            GuidedEpisodeWizard(
                new_context,
                ProductionWizardCompletion(new_context),
            ),
            name="new",
        )

        if not first_run_readiness(setup_context).setup_ready:
            self.push_screen("setup")

    def action_navigate(self, destination: str) -> None:
        if destination == "setup":
            self.push_screen("setup")
        elif destination == "new":
            self.push_screen("new")
        else:
            super().action_navigate(destination)


def main() -> None:
    GuidedDeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
