"""Reusable keyboard-first Textual shell for guided workflows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

from deeper_dive.diagnostics import redact, sanitize_exception_message
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_workflow import (
    CompletionProbe,
    SetupMode,
    WizardContext,
    WizardKind,
    WizardNavigator,
    WizardStep,
    WizardTransitionBlocked,
    steps_for,
)

MINIMUM_TERMINAL_WIDTH = 80
MINIMUM_TERMINAL_HEIGHT = 24
RECOMMENDED_TERMINAL_WIDTH = 100
RECOMMENDED_TERMINAL_HEIGHT = 30

# Only editable business-form controls participate in dirty detection. Navigation
# pickers, action buttons, and generated status text are intentionally excluded.
_FORM_FIELDS: dict[tuple[WizardKind, str], tuple[str, ...]] = {
    (WizardKind.FIRST_RUN, "provider-config"): (
        "setup-provider-name",
        "setup-provider-adapter",
        "setup-provider-base-url",
        "setup-provider-model",
        "setup-provider-credential-env",
        "setup-provider-network",
    ),
    (WizardKind.FIRST_RUN, "model-test"): (
        "setup-role-episode-planning",
        "setup-role-host-generation",
        "setup-role-directing",
        "setup-role-verification",
    ),
    (WizardKind.FIRST_RUN, "speech"): (
        "setup-speech-choice",
        "setup-speech-name",
        "setup-speech-adapter",
        "setup-speech-base-url",
        "setup-speech-model",
        "setup-speech-credential-env",
        "setup-speech-network",
        "setup-speech-voices",
    ),
    (WizardKind.FIRST_RUN, "voice-defaults"): (
        "setup-host1-voice",
        "setup-host2-voice",
        "setup-duration",
        "setup-research-default",
    ),
    (WizardKind.NEW_DEEP_DIVE, "project"): (
        "guided-project-name",
        "guided-project-topic",
        "guided-project-audience",
        "guided-project-description",
    ),
    (WizardKind.NEW_DEEP_DIVE, "sources"): (
        "guided-source-title",
        "guided-source-text",
        "guided-source-paths",
        "guided-source-urls",
    ),
    (WizardKind.NEW_DEEP_DIVE, "research"): ("guided-research-policy",),
    (WizardKind.NEW_DEEP_DIVE, "hosts"): (
        "guided-host-name",
        "guided-host-role",
        "guided-host-expertise",
        "guided-host-instructions",
    ),
    (WizardKind.NEW_DEEP_DIVE, "episode"): (
        "guided-episode-title",
        "guided-episode-focus",
        "guided-episode-duration",
        "guided-episode-custom-duration",
        "guided-episode-audience",
        "guided-episode-depth",
        "guided-episode-must-cover",
        "guided-episode-avoid",
    ),
    (WizardKind.NEW_DEEP_DIVE, "plan"): (
        "guided-plan-title",
        "guided-plan-purpose",
        "guided-plan-duration",
    ),
}


class WizardShell(Screen[None]):
    """One shared shell for first-run and New Deep Dive guided workflows.

    Concrete workflows supply production-derived completion and step content while
    this class owns progress, navigation, focusable actions, busy-state protection,
    help/status surfaces, and compact-terminal behavior.
    """

    BINDINGS = [
        Binding("escape", "save_exit", "Save and Exit"),
        Binding("space", "activate_focused_button", "Activate button", show=False),
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
    #wizard-exit-confirmation { display: none; height: auto; padding: 0 1; }
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
        self._error_details: str | None = None
        self._exit_confirmation_pending = False
        self._pending_transition: str | None = None
        self._last_form_status = ""
        self._form_baselines: dict[str, tuple[tuple[str, str], ...]] = {}
        self._viewport_width = RECOMMENDED_TERMINAL_WIDTH

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
            yield Static(
                str(redact(self.step_content(navigator.current_step.key))),
                id="wizard-step-content",
                markup=False,
            )
            yield from self.step_controls()
        yield Static(
            str(redact(self._status_text(navigator.current_step.key))),
            id="wizard-status",
            markup=False,
        )
        with Horizontal(id="wizard-actions"):
            yield Button("Back", id="wizard-back", name="back")
            yield Button("Continue", id="wizard-continue", name="continue", variant="primary")
            yield Button("Save and Exit", id="wizard-save-exit", name="save-exit")
            yield Button("Help", id="wizard-help", name="help")
        with Horizontal(id="wizard-exit-confirmation"):
            yield Button("Save changes and exit", id="wizard-confirm-save", name="confirm-save")
            yield Button(
                "Exit without changes", id="wizard-confirm-discard", name="confirm-discard"
            )
            yield Button(
                "Continue editing",
                id="wizard-confirm-cancel",
                name="confirm-cancel",
                variant="primary",
            )
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
        self._schedule_form_baseline()

    def on_resize(self, event: events.Resize) -> None:
        self._apply_viewport_policy(event.size.width, event.size.height)

    def action_activate_focused_button(self) -> None:
        """Activate a focused shared-shell button exactly once on Space."""
        focused = self.focused
        if not isinstance(focused, Button) or focused.disabled:
            return
        action = focused.name or ""
        handlers = {
            "back": self.action_back,
            "continue": self.action_continue,
            "save-exit": self.action_save_exit,
            "help": self.action_help,
            "confirm-save": self.action_confirm_save_exit,
            "confirm-discard": self.action_confirm_discard_exit,
            "confirm-cancel": self.action_cancel_exit_confirmation,
        }
        handler = handlers.get(action)
        if handler is not None:
            handler()

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
        elif action == "confirm-save":
            self.action_confirm_save_exit()
        elif action == "confirm-discard":
            self.action_confirm_discard_exit()
        elif action == "confirm-cancel":
            self.action_cancel_exit_confirmation()

    def step_content(self, step_key: str) -> str:
        """Return concrete workflow content; subclasses replace this per step."""

        return f"Guided workflow step: {step_key}"

    def step_controls(self) -> tuple[Widget, ...]:
        """Optional workflow controls within the scrolling step content."""

        return ()

    def blocker_message(self, step_key: str) -> str:
        """Return the first actionable blocker for a required incomplete step."""

        return f"Complete {step_key.replace('-', ' ')} before continuing."

    def action_back(self) -> bool:
        if self.busy or self._exit_confirmation_pending:
            return False
        if self._current_form_dirty():
            self._request_dirty_transition("back")
            return False
        previous = self.context.state
        self.context.state = self.navigator.back()
        if self.context.state == previous:
            return False
        self._sync_text()
        self._schedule_form_baseline()
        return True

    def action_continue(self) -> bool:
        if self.busy or self._exit_confirmation_pending:
            return False
        if self._current_form_dirty():
            self._request_dirty_transition("continue")
            return False
        previous = self.context.state
        try:
            self.context.state = self.navigator.continue_forward()
        except WizardTransitionBlocked as exc:
            # A dependency can become invalid while the wizard is open.
            recovered = self.navigator.recovered_state()
            if recovered != self.context.state:
                self.context.state = recovered
                self._sync_text()
            self.set_status(self.blocker_message(exc.step_key))
            return False
        if self.context.state == previous:
            return False
        self._sync_text()
        self._schedule_form_baseline()
        return True

    def request_external_navigation(self, destination: str) -> bool:
        """Return True when a dirty wizard consumed a global navigation request."""

        if self.busy or self._exit_confirmation_pending:
            return True
        if not self._current_form_dirty():
            return False
        self._request_dirty_transition(f"navigate:{destination}")
        return True

    def _request_dirty_transition(self, transition: str) -> None:
        self._pending_transition = transition
        self._exit_confirmation_pending = True
        self._sync_exit_confirmation()
        labels = {
            "exit": "exit",
            "back": "go back",
            "continue": "continue",
        }
        destination = labels.get(transition, "leave this screen")
        self.set_status(
            "Unsaved changes. Save changes and "
            f"{destination}, explicitly discard them, or continue editing."
        )
        self.query_one("#wizard-confirm-cancel", Button).focus()

    def _editable_snapshot(self) -> tuple[tuple[str, str], ...]:
        keys = _FORM_FIELDS.get((self.context.state.kind, self.context.state.current_step), ())
        values: list[tuple[str, str]] = []
        for key in keys:
            try:
                widget = self.query_one(f"#{key}")
            except NoMatches:
                # The abstract shared shell does not mount concrete wizard fields.
                continue
            if isinstance(widget, (Input, Select)):
                values.append((key, str(widget.value)))
        return tuple(values)

    def _schedule_form_baseline(self) -> None:
        # Do not turn edits made before Textual's next refresh into the baseline.
        # Rehydration may also happen between scheduling and that refresh.
        step = self.context.state.current_step
        snapshot = self._editable_snapshot()

        def remember_if_unchanged() -> None:
            if self.context.state.current_step == step and self._editable_snapshot() == snapshot:
                self._form_baselines[step] = snapshot

        self.call_after_refresh(remember_if_unchanged)

    def _remember_current_form(self) -> None:
        self._form_baselines[self.context.state.current_step] = self._editable_snapshot()

    def _current_form_dirty(self) -> bool:
        snapshot = self._editable_snapshot()
        baseline = self._form_baselines.get(self.context.state.current_step)
        if baseline is None:
            # Fail closed before the first post-mount snapshot can be captured.
            return bool(snapshot)
        return snapshot != baseline

    def action_save_exit(self) -> None:
        if self.busy:
            return
        if self._exit_confirmation_pending:
            self.action_cancel_exit_confirmation()
            return
        if self._current_form_dirty():
            self._request_dirty_transition("exit")
            return
        self._checkpoint_and_exit()

    def _checkpoint_and_exit(self) -> None:
        store = GuidedDraftStore(self.context.composition.service.workspaces.data_dir)
        try:
            store.save(self.context)
        except (OSError, ValueError) as exc:
            self.set_status("Could not save wizard progress: " + sanitize_exception_message(exc))
            return
        self._clear_transition_confirmation()
        self.save_exit_requested = True
        self.set_status("Progress checkpoint saved; safe to resume from this checkpoint.")
        self.on_save_exit()

    def _save_dirty_step(self) -> bool:
        """Subclasses delegate to their existing production-backed save action."""
        self.set_status("Save this step using its production Save action before continuing.")
        return False

    def action_confirm_save_exit(self) -> None:
        if not self._exit_confirmation_pending or self.busy:
            return
        transition = self._pending_transition or "exit"
        self._clear_transition_confirmation()
        try:
            saved = self._save_dirty_step()
        except (OSError, KeyError, RuntimeError, ValueError) as exc:
            self.set_error("Could not save changes.", exc)
            return
        if not saved:
            return
        self._remember_current_form()
        self._execute_pending_transition(transition)

    def action_confirm_discard_exit(self) -> None:
        if not self._exit_confirmation_pending or self.busy:
            return
        transition = self._pending_transition or "exit"
        self._clear_transition_confirmation()
        # Mark only the UI snapshot clean so the requested transition can occur.
        # No business data is persisted by an explicit discard.
        self._remember_current_form()
        self._execute_pending_transition(transition)

    def action_cancel_exit_confirmation(self) -> None:
        if not self._exit_confirmation_pending:
            return
        self._clear_transition_confirmation()
        self.set_status("Continuing to edit; unsaved changes are still present.")

    def _execute_pending_transition(self, transition: str) -> None:
        if transition == "exit":
            self._checkpoint_and_exit()
        elif transition == "back":
            self.action_back()
        elif transition == "continue":
            self.action_continue()
        elif transition.startswith("navigate:"):
            navigate = getattr(self.app, "action_navigate", None)
            if not callable(navigate):
                raise RuntimeError("wizard app does not support navigation")
            navigate(transition.split(":", 1)[1])
        else:
            self._execute_custom_transition(transition)

    def _execute_custom_transition(self, transition: str) -> None:
        raise ValueError(f"unsupported wizard transition {transition!r}")

    def _clear_transition_confirmation(self) -> None:
        self._exit_confirmation_pending = False
        self._pending_transition = None
        self._sync_exit_confirmation()

    def _sync_exit_confirmation(self) -> None:
        pending = self._exit_confirmation_pending
        transition = self._pending_transition or "exit"
        labels = {
            "exit": ("Save changes and exit", "Exit without changes"),
            "back": ("Save changes and go back", "Discard changes and go back"),
            "continue": ("Save changes and continue", "Discard changes and continue"),
        }
        save_label, discard_label = labels.get(
            transition,
            ("Save changes and leave", "Discard changes and leave"),
        )
        self.query_one("#wizard-confirm-save", Button).label = save_label
        self.query_one("#wizard-confirm-discard", Button).label = discard_label
        self.query_one("#wizard-exit-confirmation", Horizontal).display = pending
        self._sync_actions()

    def action_help(self) -> None:
        self.help_requested = True
        details = self._error_details
        message = self.help_text(self.navigator.current_step.key)
        if details:
            message += f"\nDetails: {details}"
        self.set_status(message)
        self._error_details = details

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

    def set_error(self, summary: str, exc: BaseException) -> None:
        self.set_status(f"{summary} Press F1 for details.")
        self._error_details = sanitize_exception_message(exc)

    def set_status(self, message: str) -> None:
        self._last_form_status = message
        self._error_details = None
        self.query_one("#wizard-status", Static).update(str(redact(message)))

    def _sync_text(self, *, preserve_status: bool = False) -> None:
        navigator = self.navigator
        self.query_one("#wizard-heading", Label).update(self._heading_text(navigator))
        self.query_one("#wizard-progress", Static).update(self._progress_text(navigator))
        self.query_one("#wizard-step-content", Static).update(
            str(redact(self.step_content(navigator.current_step.key)))
        )
        if not preserve_status:
            self.query_one("#wizard-status", Static).update(
                str(redact(self._status_text(navigator.current_step.key)))
            )
        self._sync_actions()

    def _sync_actions(self) -> None:
        navigator = self.navigator
        pending = self._exit_confirmation_pending
        self.query_one("#wizard-back", Button).disabled = (
            self.busy or pending or navigator.current_index == 0
        )
        self.query_one("#wizard-continue", Button).disabled = (
            self.busy or pending or not navigator.can_continue
        )
        self.query_one("#wizard-save-exit", Button).disabled = self.busy or pending
        self.query_one("#wizard-exit-confirmation", Horizontal).display = pending

    def _apply_viewport_policy(self, width: int, height: int) -> None:
        self._viewport_width = width
        self.query_one("#wizard-progress", Static).update(self._progress_text(self.navigator))
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
        """Keep the progress rail on one line, including at 80 columns.

        Prior/current/next context is included only when it fits the viewport.
        Full step completion remains available from the derived navigator.
        """
        progress = navigator.progress()
        index = navigator.current_index
        current = progress[index]
        prefix = f"{index + 1}/{len(progress)}"
        current_label = f"{current.text_marker} {current.label} ({current.visual_state.value})"
        complete = sum(item.visual_state.value == "complete" for item in progress)
        needs_attention = sum(item.visual_state.value == "needs-attention" for item in progress)
        summary = f"✓ {complete} done"
        if needs_attention:
            summary += f", ! {needs_attention} need attention"
        result = f"{prefix} | {current_label} | {summary}"
        budget = max(30, self._viewport_width - 4)
        if index:
            previous = progress[index - 1]
            candidate = (
                f"{prefix} | {previous.text_marker} {previous.label} "
                f"({previous.visual_state.value}) | {current_label} | {summary}"
            )
            if len(candidate) <= budget:
                result = candidate
        # Prefer the next genuinely upcoming step, which may be farther
        # ahead than an already-ready intermediate prerequisite.
        upcoming = next(
            (item for item in progress[index + 1 :] if item.visual_state.value == "upcoming"),
            None,
        )
        following = upcoming or (progress[index + 1] if index + 1 < len(progress) else None)
        if following is not None:
            suffix = (
                f" | {following.text_marker} {following.label} ({following.visual_state.value})"
            )
            if len(result) + len(suffix) <= budget:
                result += suffix
        return result

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
