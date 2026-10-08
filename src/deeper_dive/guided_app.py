"""Production entry point for the guided Textual startup workflow."""

from __future__ import annotations

from deeper_dive.guided_readiness import ProductionWizardCompletion, first_run_readiness
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.wizard_shell import FirstRunWizardShell


class GuidedDeeperDiveApp(DeeperDiveApp):
    """Launch setup only when durable provider/default readiness is incomplete."""

    def on_ready(self) -> None:
        # The base app installs and pushes Home during on_mount. Textual dispatches
        # lifecycle handlers across the inheritance chain, so installing Home again
        # in a subclass on_mount would raise ScreenError.
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
        else:
            super().action_navigate(destination)


def main() -> None:
    GuidedDeeperDiveApp().run()


if __name__ == "__main__":  # pragma: no cover
    main()
