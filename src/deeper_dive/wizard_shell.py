"""Reusable keyboard-first Textual shell for guided workflows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Label, Select, Static

from deeper_dive.diagnostics import redact
from deeper_dive.guided_workflow import (
    CompletionProbe,
    SetupMode,
    WizardContext,
    WizardNavigator,
    WizardStep,
    WizardTransitionBlocked,
    steps_for,
)

MINIMUM_TERMINAL_WIDTH = 80
MINIMUM_TERMINAL_HEIGHT = 24
RECOMMENDED_TERMINAL_WIDTH = 100
RECOMMENDED_TERMINAL_HEIGHT = 30


class WizardShell(Screen[None]):
    """One shared shell for first-run and New Deep Dive guided workflows.

    Concrete workflows supply production-derived completion and step content while
    this class owns progress, navigation, focusable actions, busy-state protection,
    help/status surfaces, and compact-terminal behavior.
    """

    BINDINGS = [
        Binding("escape", "save_exit", "Save and Exit"),
        Binding("f1", "help", "Help"),
        Binding("?", "help", "Help"),
    ]

    CSS = """
    #wizard-heading { text-style: bold; padding: 0 1; }
    #wizard-progress { padding: 0 1; margin-bottom: 1; }
    #wizard-content { padding: 0 1; min-height: 4; }
    #wizard-status { padding: 0 1; margin-top: 1; }
    #wizard-actions { height: auto; padding: 0 1; }
    #wizard-actions Button { min-width: 12; margin-right: 1; }
    #wizard-resize-message { display: none; padding: 1; text-style: bold; }
    """

    def __init__(
        self,
        context: WizardContext,
        completion_probe: CompletionProbe,
        *,
        title: str,
        steps: Sequence[WizardStep] | None = None,
        status_provider: Callable[[str], str] | None = None,
    ) -> None:
        super().__init__(id=f"screen-wizard-{context.state.kind.value}")
        self.context = context
        self.title_text = title
        self.steps = tuple(steps or steps_for(context.state.kind))
        self.completion_probe = completion_probe
        self.status_provider = status_provider
        self.busy = False
        self.save_exit_requested = False
        self.help_requested = False

    @property
    def navigator(self) -> WizardNavigator:
        """Build navigation from current state so completion is always freshly derived."""

        return WizardNavigator(self.context.state, self.completion_probe, steps=self.steps)

    def compose(self) -> ComposeResult:
        navigator = self.navigator
        yield Header()
        yield Label(self._heading_text(navigator), id="wizard-heading")
        yield Static(self._progress_text(navigator), id="wizard-progress")
        yield Static("", id="wizard-resize-message")
        with VerticalScroll(id="wizard-content"):
            yield Static(self.step_content(navigator.current_step.key), id="wizard-step-content")
            yield from self.step_controls()
        yield Static(self._status_text(navigator.current_step.key), id="wizard-status")
        with Horizontal(id="wizard-actions"):
            yield Button("Back", id="wizard-back", name="back")
            yield Button("Continue", id="wizard-continue", name="continue", variant="primary")
            yield Button("Save and Exit", id="wizard-save-exit", name="save-exit")
            yield Button("Help", id="wizard-help", name="help")
        yield Footer()

    def on_mount(self) -> None:
        # Production prerequisites may change between sessions; a saved step is
        # only a hint and must be validated before it is shown to the user.
        recovered = self.navigator.recovered_state()
        if recovered != self.context.state:
            self.context.state = recovered
            self._sync_text()
        else:
            self._sync_actions()
        self._apply_viewport_policy(self.app.size.width, self.app.size.height)

    def on_resize(self, event: events.Resize) -> None:
        self._apply_viewport_policy(event.size.width, event.size.height)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        action = event.button.name
        if action == "back":
            self.action_back()
        elif action == "continue":
            self.action_continue()
        elif action == "save-exit":
            self.action_save_exit()
        elif action == "help":
            self.action_help()

    def step_content(self, step_key: str) -> str:
        """Return concrete workflow content; subclasses replace this per step."""

        return f"Guided workflow step: {step_key}"

    def step_controls(self) -> tuple[Widget, ...]:
        """Optional workflow controls within the scrolling step content."""

        return ()

    def blocker_message(self, step_key: str) -> str:
        """Return the first actionable blocker for a required incomplete step."""

        return f"Complete {step_key.replace('-', ' ')} before continuing."

    def action_back(self) -> None:
        if self.busy:
            return
        self.context.state = self.navigator.back()
        self._sync_text()

    def action_continue(self) -> None:
        if self.busy:
            return
        try:
            self.context.state = self.navigator.continue_forward()
        except WizardTransitionBlocked as exc:
            # A dependency can become invalid while the wizard is open.
            recovered = self.navigator.recovered_state()
            if recovered != self.context.state:
                self.context.state = recovered
                self._sync_text()
            self.set_status(self.blocker_message(exc.step_key))
            return
        self._sync_text()

    def action_save_exit(self) -> None:
        if self.busy:
            return
        self.save_exit_requested = True
        self.set_status("Progress is safe to resume; leaving the guided workflow.")
        self.on_save_exit()

    def action_help(self) -> None:
        self.help_requested = True
        self.set_status(self.help_text(self.navigator.current_step.key))

    def on_save_exit(self) -> None:
        """Hook for concrete workflows to persist minimal draft state and navigate away."""

    def help_text(self, step_key: str) -> str:
        return f"Help: {step_key.replace('-', ' ')}. Use Tab/Shift+Tab to move focus."

    def set_busy(self, busy: bool, message: str | None = None) -> None:
        """Disable unsafe duplicate actions while a production operation is running."""

        self.busy = busy
        self._sync_actions()
        if message is not None:
            self.set_status(message)

    def set_status(self, message: str) -> None:
        self.query_one("#wizard-status", Static).update(str(redact(message)))

    def _sync_text(self) -> None:
        navigator = self.navigator
        self.query_one("#wizard-heading", Label).update(self._heading_text(navigator))
        self.query_one("#wizard-progress", Static).update(self._progress_text(navigator))
        self.query_one("#wizard-step-content", Static).update(
            self.step_content(navigator.current_step.key)
        )
        self.query_one("#wizard-status", Static).update(
            self._status_text(navigator.current_step.key)
        )
        self._sync_actions()

    def _sync_actions(self) -> None:
        navigator = self.navigator
        self.query_one("#wizard-back", Button).disabled = self.busy or navigator.current_index == 0
        self.query_one("#wizard-continue", Button).disabled = (
            self.busy or not navigator.can_continue
        )
        self.query_one("#wizard-save-exit", Button).disabled = self.busy

    def _apply_viewport_policy(self, width: int, height: int) -> None:
        too_small = width < MINIMUM_TERMINAL_WIDTH or height < MINIMUM_TERMINAL_HEIGHT
        warning = self.query_one("#wizard-resize-message", Static)
        content = self.query_one("#wizard-content", VerticalScroll)
        actions = self.query_one("#wizard-actions", Horizontal)
        if too_small:
            warning.update(
                "Terminal too small. Resize to at least "
                f"{MINIMUM_TERMINAL_WIDTH}x{MINIMUM_TERMINAL_HEIGHT}. "
                "Your workflow state is preserved."
            )
        warning.display = too_small
        content.display = not too_small
        actions.display = not too_small

    def _heading_text(self, navigator: WizardNavigator) -> str:
        return (
            f"{self.title_text} — Step {navigator.current_index + 1} "
            f"of {len(navigator.steps)}: {navigator.current_step.label}"
        )

    def _progress_text(self, navigator: WizardNavigator) -> str:
        return "  ".join(
            f"{item.text_marker} {item.label} ({item.visual_state.value})"
            for item in navigator.progress()
        )

    def _status_text(self, step_key: str) -> str:
        if self.status_provider is not None:
            return self.status_provider(step_key)
        if self.completion_probe(step_key):
            return "Status: Ready to continue."
        return f"Status: {self.blocker_message(step_key)}"


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

    def action_continue(self) -> None:
        super().action_continue()
        self._show_welcome_controls()

    def action_back(self) -> None:
        super().action_back()
        self._show_welcome_controls()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "setup-mode" and isinstance(event.value, str):
            self.context.state = replace(self.context.state, setup_mode=SetupMode(event.value))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.name == "skip-setup":
            self.on_save_exit()
        elif event.button.name == "system-check-details":
            self._system_details_visible = not getattr(self, "_system_details_visible", False)
            self._sync_text()
        else:
            super().on_button_pressed(event)

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
