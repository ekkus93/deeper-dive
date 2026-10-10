"""Reusable keyboard-first Textual shell for guided workflows."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

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


class WizardSaveOutcome(StrEnum):
    SAVED = "saved"
    NOOP = "noop"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class WizardSaveResult:
    outcome: WizardSaveOutcome
    message: str = ""

    @property
    def can_continue(self) -> bool:
        return self.outcome in {WizardSaveOutcome.SAVED, WizardSaveOutcome.NOOP}

    @classmethod
    def from_bool(cls, saved: bool) -> WizardSaveResult:
        outcome = WizardSaveOutcome.SAVED if saved else WizardSaveOutcome.FAILED
        return cls(outcome)


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
