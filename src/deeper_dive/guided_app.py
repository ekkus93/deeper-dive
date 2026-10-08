"""Production entry point for the guided Textual startup workflow."""

from __future__ import annotations

from deeper_dive.guided_readiness import ProductionWizardCompletion, first_run_readiness
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.tui import DeeperDiveApp, HomeProjectsScreen
from deeper_dive.wizard_shell import FirstRunWizardShell


class GuidedDeeperDiveApp(DeeperDiveApp):
    """Launch setup only when durable provider/default readiness is incomplete."""

    def on_mount(self) -> None:
        self.install_screen(HomeProjectsScreen(), name="home")
        context = WizardContext(self.composition, WizardState(WizardKind.FIRST_RUN, "welcome"))
        self.install_screen(
            FirstRunWizardShell(context, ProductionWizardCompletion(context)),
            name="setup",
        )
        self.push_screen("home" if first_run_readiness(context).setup_ready else "setup")

    def action_navigate(self, destination: str) -> None:
        if destination == "setup":
            self.push_screen("setup")
        else:
            super().action_navigate(destination)


def main() -> None:
    GuidedDeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
