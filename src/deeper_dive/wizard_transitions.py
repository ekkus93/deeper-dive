"""Typed transitions, dirty-form snapshots, and form-field registry for guided wizards."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from deeper_dive.guided_workflow import WizardKind


@dataclass(frozen=True, slots=True)
class TransitionLabels:
    """User-facing wording for one pending dirty-form transition."""

    action: str
    save: str
    discard: str


class TransitionKind(StrEnum):
    """Every dirty-form transition a guided wizard can defer behind a prompt."""

    NAVIGATE = "navigate"
    EXIT = "exit"
    BACK = "back"
    CONTINUE = "continue"
    PLAN_BUILD = "plan-build"
    DISCOVER_MODELS = "discover-models"
    RECOMMENDED_ROLES = "recommended-roles"
    DISCOVER_VOICES = "discover-voices"
    CREATE_HOST = "create-host"
    CREATE_RECOMMENDED_HOSTS = "create-recommended-hosts"
    PLAN_REGENERATE = "plan-regenerate"
    PLAN_REGENERATE_SEGMENT = "plan-regenerate-segment"
    PREFLIGHT_FIX = "preflight-fix"
    GENERATION_START = "generation-start"
    HOST_SELECT = "host-select"
    PLAN_SELECT = "plan-select"
    SPEECH_CHOICE = "speech-choice"


@dataclass(frozen=True, slots=True)
class Transition:
    """A pending dirty-form transition: a kind plus its destination, if it has one."""

    kind: TransitionKind
    argument: str | None = None

    @property
    def encoded(self) -> str:
        return self.kind.value if self.argument is None else f"{self.kind.value}:{self.argument}"

    def __str__(self) -> str:
        return self.encoded


# Single source of truth for every transition kind. Parameterized kinds carry
# their argument after a colon ("navigate:home", "host-select:<id>").
_TRANSITION_LABELS: dict[TransitionKind, TransitionLabels] = {
    TransitionKind.EXIT: TransitionLabels("exit", "Save changes and exit", "Exit without changes"),
    TransitionKind.BACK: TransitionLabels(
        "go back", "Save changes and go back", "Discard changes and go back"
    ),
    TransitionKind.CONTINUE: TransitionLabels(
        "continue", "Save changes and continue", "Discard changes and continue"
    ),
    TransitionKind.PLAN_BUILD: TransitionLabels(
        "build the plan", "Save segment then build plan", "Discard edits then build plan"
    ),
    TransitionKind.DISCOVER_MODELS: TransitionLabels(
        "discover models",
        "Save provider then discover models",
        "Discard edits then discover models",
    ),
    TransitionKind.RECOMMENDED_ROLES: TransitionLabels(
        "apply recommended model roles",
        "Save role edits then apply recommendations",
        "Discard edits then apply recommendations",
    ),
    TransitionKind.DISCOVER_VOICES: TransitionLabels(
        "discover voices",
        "Save defaults then discover voices",
        "Discard edits then discover voices",
    ),
    TransitionKind.CREATE_HOST: TransitionLabels(
        "create a host",
        "Save host then create a new host",
        "Discard edits then create a new host",
    ),
    TransitionKind.CREATE_RECOMMENDED_HOSTS: TransitionLabels(
        "create the recommended hosts",
        "Save host then create recommended hosts",
        "Discard edits then create recommended hosts",
    ),
    TransitionKind.PLAN_REGENERATE: TransitionLabels(
        "regenerate the plan",
        "Save segment then regenerate plan",
        "Discard edits then regenerate plan",
    ),
    TransitionKind.PLAN_REGENERATE_SEGMENT: TransitionLabels(
        "regenerate the selected segment",
        "Save segment then regenerate",
        "Discard edits then regenerate",
    ),
    TransitionKind.PREFLIGHT_FIX: TransitionLabels(
        "repair the preflight blocker", "Save edits then repair", "Discard edits then repair"
    ),
    TransitionKind.GENERATION_START: TransitionLabels(
        "start generation",
        "Save edits then start generation",
        "Discard edits then start generation",
    ),
    TransitionKind.HOST_SELECT: TransitionLabels(
        "select another host",
        "Save host then select the other host",
        "Discard edits then select the other host",
    ),
    TransitionKind.PLAN_SELECT: TransitionLabels(
        "select another plan",
        "Save plan edits then select the other plan",
        "Discard plan edits then select the other plan",
    ),
    TransitionKind.SPEECH_CHOICE: TransitionLabels(
        "switch speech providers",
        "Save speech settings then switch",
        "Discard speech edits then switch",
    ),
}


def transition_kinds() -> frozenset[TransitionKind]:
    """Every labelled transition kind (including parameterized kinds and navigate)."""

    return frozenset(_TRANSITION_LABELS) | {TransitionKind.NAVIGATE}


def describe_transition(transition: Transition) -> TransitionLabels:
    """Return the wording for a typed transition."""

    if transition.kind is TransitionKind.NAVIGATE:
        target = (transition.argument or "").replace("-", " ")
        return TransitionLabels(
            "go to " + target,
            f"Save changes and go to {target.title()}",
            f"Discard changes and go to {target.title()}",
        )
    return _TRANSITION_LABELS[transition.kind]


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


@dataclass(frozen=True, slots=True)
class WizardDirtyFormSnapshot:
    """Loss-safe, typed identity and values used by all guided dirty guards.

    Displayed values are exact user inputs; semantic values normalize only
    fields whose production save strips whitespace. A target-identity change
    is dirty until a production hydration/save records a fresh baseline.
    """

    kind: WizardKind
    step_key: str
    target_identity: tuple[str | None, str | None, str | None]
    baseline_identity: tuple[str | None, str | None, str | None] | None
    durable_baseline: tuple[tuple[str, str], ...] | None
    displayed_values: tuple[tuple[str, str], ...]
    semantic_snapshot: tuple[tuple[str, str], ...]
    original_destination: Transition | None

    @property
    def dirty(self) -> bool:
        if self.durable_baseline is None:
            return bool(self.displayed_values)
        return self.displayed_values != self.durable_baseline or (
            self.baseline_identity is not None and self.target_identity != self.baseline_identity
        )


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
