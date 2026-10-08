"""Shared state and transition policy for guided Textual workflows.

The guided workflow layer deliberately keeps production entities in their existing
repositories/services.  Wizard state contains only production identities plus the
small amount of UI navigation metadata that cannot be reconstructed from durable
production state.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from deeper_dive.composition import ProductionComposition

WIZARD_STATE_SCHEMA_VERSION: Final = 1


class WizardKind(StrEnum):
    """Supported guided workflows."""

    FIRST_RUN = "first-run"
    NEW_DEEP_DIVE = "new-deep-dive"


class SetupMode(StrEnum):
    """First-run setup depth; this is UI navigation state, not provider state."""

    QUICK = "quick"
    ADVANCED = "advanced"


class WizardStepVisualState(StrEnum):
    """Accessible progress state rendered by the shared wizard shell."""

    COMPLETE = "complete"
    CURRENT = "current"
    UPCOMING = "upcoming"
    NEEDS_ATTENTION = "needs-attention"


@dataclass(frozen=True, slots=True)
class WizardStep:
    """One stable wizard step definition."""

    key: str
    label: str
    skippable: bool = False


FIRST_RUN_STEPS: Final[tuple[WizardStep, ...]] = (
    WizardStep("welcome", "Welcome"),
    WizardStep("system-check", "System Check"),
    WizardStep("ai-provider", "AI Provider"),
    WizardStep("provider-config", "Configure Provider"),
    WizardStep("model-test", "Model Test"),
    WizardStep("speech", "Speech"),
    WizardStep("voice-defaults", "Voice & Defaults"),
    WizardStep("ready", "Ready"),
)

NEW_DEEP_DIVE_STEPS: Final[tuple[WizardStep, ...]] = (
    WizardStep("project", "Project Setup"),
    WizardStep("sources", "Sources"),
    WizardStep("research", "Research"),
    WizardStep("hosts", "Hosts"),
    WizardStep("episode", "Episode Settings"),
    WizardStep("plan", "Review & Plan"),
    WizardStep("preflight", "Ready to Generate"),
)


def steps_for(kind: WizardKind) -> tuple[WizardStep, ...]:
    """Return the stable ordered step definitions for one workflow."""

    if kind is WizardKind.FIRST_RUN:
        return FIRST_RUN_STEPS
    return NEW_DEEP_DIVE_STEPS


@dataclass(frozen=True, slots=True)
class WizardState:
    """Minimal versioned UI-only navigation state.

    This record intentionally excludes provider configuration, source content, host
    definitions, episode configuration, plans, runs, turns, audio, and exports.
    Those remain owned by production services and repositories.
    """

    kind: WizardKind
    current_step: str
    schema_version: int = WIZARD_STATE_SCHEMA_VERSION
    setup_mode: SetupMode | None = None

    def __post_init__(self) -> None:
        if self.schema_version != WIZARD_STATE_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported wizard state schema {self.schema_version}; "
                f"expected {WIZARD_STATE_SCHEMA_VERSION}"
            )
        keys = {step.key for step in steps_for(self.kind)}
        if self.current_step not in keys:
            raise ValueError(f"unknown {self.kind.value} wizard step {self.current_step!r}")
        if self.kind is WizardKind.NEW_DEEP_DIVE and self.setup_mode is not None:
            raise ValueError("setup_mode is only valid for first-run wizard state")

    def moved_to(self, step_key: str) -> WizardState:
        """Return a copy at another validated step."""

        return replace(self, current_step=step_key)

    def to_record(self) -> dict[str, object]:
        """Serialize only the explicitly permitted UI draft fields."""

        return {
            "schema_version": self.schema_version,
            "kind": self.kind.value,
            "current_step": self.current_step,
            "setup_mode": self.setup_mode.value if self.setup_mode is not None else None,
        }

    @classmethod
    def from_record(cls, raw: Mapping[str, object]) -> WizardState:
        """Load a versioned draft, rejecting unknown or corrupt state safely."""

        allowed = {"schema_version", "kind", "current_step", "setup_mode"}
        extra = set(raw) - allowed
        if extra:
            raise ValueError(f"wizard state contains unsupported fields: {sorted(extra)!r}")
        version = raw.get("schema_version")
        if not isinstance(version, int):
            raise ValueError("wizard state schema_version must be an integer")
        kind_raw = raw.get("kind")
        step_raw = raw.get("current_step")
        setup_raw = raw.get("setup_mode")
        if not isinstance(kind_raw, str) or not isinstance(step_raw, str):
            raise ValueError("wizard state kind/current_step must be strings")
        setup_mode = None
        if setup_raw is not None:
            if not isinstance(setup_raw, str):
                raise ValueError("wizard state setup_mode must be a string or null")
            setup_mode = SetupMode(setup_raw)
        return cls(
            kind=WizardKind(kind_raw),
            current_step=step_raw,
            schema_version=version,
            setup_mode=setup_mode,
        )


@dataclass(slots=True)
class WizardContext:
    """Typed runtime boundary joining UI navigation to production state.

    The composition remains the single production application context.  Only stable
    IDs are retained here; screens reload the corresponding entities through the
    normal production services on every operation.
    """

    composition: ProductionComposition
    state: WizardState
    project_id: str | None = None
    episode_id: str | None = None
    run_id: str | None = None


CompletionProbe = Callable[[str], bool]


@dataclass(frozen=True, slots=True)
class WizardProgressItem:
    """One derived progress row for rendering and accessibility tests."""

    key: str
    label: str
    visual_state: WizardStepVisualState

    @property
    def text_marker(self) -> str:
        """Return a non-color marker for the visual state."""

        return {
            WizardStepVisualState.COMPLETE: "[x]",
            WizardStepVisualState.CURRENT: "[>]",
            WizardStepVisualState.UPCOMING: "[ ]",
            WizardStepVisualState.NEEDS_ATTENTION: "[!]",
        }[self.visual_state]


class WizardNavigator:
    """Derived transition policy shared by both guided workflows."""

    def __init__(
        self,
        state: WizardState,
        completion_probe: CompletionProbe,
        *,
        steps: Sequence[WizardStep] | None = None,
    ) -> None:
        self.state = state
        self.completion_probe = completion_probe
        self.steps = tuple(steps or steps_for(state.kind))
        self._index_by_key = {step.key: index for index, step in enumerate(self.steps)}
        if state.current_step not in self._index_by_key:
            raise ValueError(f"current step {state.current_step!r} is not in this wizard")

    @property
    def current_index(self) -> int:
        return self._index_by_key[self.state.current_step]

    @property
    def current_step(self) -> WizardStep:
        return self.steps[self.current_index]

    @property
    def can_continue(self) -> bool:
        return self.current_step.skippable or self.completion_probe(self.current_step.key)

    def progress(self) -> tuple[WizardProgressItem, ...]:
        """Derive progress from production readiness instead of stored completion flags."""

        current = self.current_index
        items: list[WizardProgressItem] = []
        for index, step in enumerate(self.steps):
            complete = self.completion_probe(step.key)
            if index == current:
                visual = WizardStepVisualState.CURRENT
            elif index < current and not complete:
                visual = WizardStepVisualState.NEEDS_ATTENTION
            elif complete:
                visual = WizardStepVisualState.COMPLETE
            else:
                visual = WizardStepVisualState.UPCOMING
            items.append(WizardProgressItem(step.key, step.label, visual))
        return tuple(items)

    def back(self) -> WizardState:
        """Move backward without changing production state."""

        if self.current_index == 0:
            return self.state
        return self.state.moved_to(self.steps[self.current_index - 1].key)

    def continue_forward(self) -> WizardState:
        """Move forward only when current production-derived completion allows it."""

        if not self.can_continue:
            raise WizardTransitionBlocked(self.current_step.key)
        if self.current_index == len(self.steps) - 1:
            return self.state
        return self.state.moved_to(self.steps[self.current_index + 1].key)

    def recovered_state(self) -> WizardState:
        """Recover safely after restart or stale/corrupt prerequisite state.

        Preserve a later valid location only when every earlier non-skippable
        prerequisite still derives as complete.  Otherwise fall back to the earliest
        incomplete prerequisite.
        """

        for index, step in enumerate(self.steps[: self.current_index]):
            if not step.skippable and not self.completion_probe(step.key):
                return self.state.moved_to(self.steps[index].key)
        return self.state


class WizardTransitionBlocked(RuntimeError):
    """Raised when Continue is requested before a required step is complete."""

    def __init__(self, step_key: str) -> None:
        super().__init__(f"wizard step {step_key!r} is not complete")
        self.step_key = step_key
