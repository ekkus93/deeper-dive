"""Production entry point for the guided Textual startup workflow."""

from __future__ import annotations

from textual.binding import Binding

from deeper_dive.guided_source_wizard import GuidedSourceWizard
from deeper_dive.guided_readiness import ProductionWizardCompletion, first_run_readiness
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.wizard_shell import FirstRunWizardShell


class GuidedDeeperDiveApp(DeeperDiveApp):
    """Route first-run and New Deep Dive through the shared production context."""

    BINDINGS = [
        *DeeperDiveApp.BINDINGS,
        Binding("ctrl+g", "navigate('new')", "New Deep Dive"),
    ]

    def on_ready(self) -> None:
        # Base on_mount already installs Home; avoid duplicate lifecycle installs.
        context = WizardContext(self.composition, WizardState(WizardKind.FIRST_RUN, "welcome"))
        self.install_screen(
            FirstRunWizardShell(context, ProductionWizardCompletion(context)),
            name="setup",
        )
        if not first_run_readiness(context).setup_ready:
            self.push_screen("setup")

    def action_navigate(self, destination: str) -> None:
        if destination == "setup":
            self.push_screen("setup")
        elif destination == "new":
            context = WizardContext(
                self.composition, WizardState(WizardKind.NEW_DEEP_DIVE, "project")
            )
            self.push_screen(GuidedSourceWizard(context, ProductionWizardCompletion(context)))
        else:
            super().action_navigate(destination)


def main() -> None:
    GuidedDeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
