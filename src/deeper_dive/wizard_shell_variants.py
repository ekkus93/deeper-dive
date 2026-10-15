"""Concrete guided wizard shells layered on the shared ``WizardShell``."""

from __future__ import annotations

from dataclasses import replace

from textual.widget import Widget
from textual.widgets import Button, Select

from deeper_dive.guided_workflow import CompletionProbe, SetupMode, WizardContext
from deeper_dive.wizard_shell import WizardShell


class FirstRunWizardShell(WizardShell):
    """First-run specialization with a welcome and optional system check."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe, title="First-run Setup")

    def step_controls(self) -> tuple[Widget, ...]:
        return (
            Select(
                [
                    ("Quick Setup (recommended)", SetupMode.QUICK.value),
                    ("Advanced Setup", SetupMode.ADVANCED.value),
                ],
                value=(self.context.state.setup_mode or SetupMode.QUICK).value,
                allow_blank=False,
                id="setup-mode",
            ),
            Button("Skip Setup", id="setup-skip", name="skip-setup"),
            Button(
                "System Check Details",
                id="system-check-details",
                name="system-check-details",
            ),
        )

    def step_content(self, step_key: str) -> str:
        if step_key == "welcome":
            return (
                "Welcome to Deeper Dive. Local AI models are supported; cloud is optional.\n"
                "Quick Setup recommends defaults. Advanced Setup exposes more controls.\n"
                "Skip Setup allows project inspection without completing setup."
            )
        if step_key == "system-check":
            from deeper_dive.first_run import FirstRunController

            check = FirstRunController(self.context.composition.provider_controller).system_check()
            rows = list(check.summary())
            if getattr(self, "_system_details_visible", False):
                rows.extend(("", "Details:", *check.diagnostics))
                rows.append(
                    "Remediation: choose any healthy supported provider. "
                    "Install FFmpeg before audio generation."
                )
            return "\n".join(rows)
        return super().step_content(step_key)

    def on_mount(self) -> None:
        super().on_mount()
        self._show_welcome_controls()

    def action_continue(self) -> bool:
        if not super().action_continue():
            return False
        self._show_welcome_controls()
        self._schedule_form_baseline()
        return True

    def action_back(self) -> bool:
        if not super().action_back():
            return False
        self._show_welcome_controls()
        self._schedule_form_baseline()
        return True

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "setup-mode" and isinstance(event.value, str):
            self.context.state = replace(self.context.state, setup_mode=SetupMode(event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name == "skip-setup":
            self.on_save_exit()
        elif event.button.name == "system-check-details":
            self._system_details_visible = not getattr(self, "_system_details_visible", False)
            self._sync_text()
        # Textual dispatches WizardShell.on_button_pressed itself; no super() call.

    def on_save_exit(self) -> None:
        try:
            self.app.get_screen("home")
        except KeyError:
            return
        self.app.push_screen("home")

    def _show_welcome_controls(self) -> None:
        welcome = self.context.state.current_step == "welcome"
        system_check = self.context.state.current_step == "system-check"
        self.query_one("#setup-mode", Select).display = welcome
        self.query_one("#setup-skip", Button).display = welcome
        self.query_one("#system-check-details", Button).display = system_check


class NewDeepDiveWizardShell(WizardShell):
    """New Deep Dive specialization using the same shared shell contract."""

    def __init__(self, context: WizardContext, completion_probe: CompletionProbe) -> None:
        super().__init__(context, completion_probe, title="New Deep Dive")
