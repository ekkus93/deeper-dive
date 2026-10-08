from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.guided_workflow import (
    FIRST_RUN_STEPS,
    NEW_DEEP_DIVE_STEPS,
    SetupMode,
    WizardContext,
    WizardKind,
    WizardNavigator,
    WizardState,
    WizardStepVisualState,
    WizardTransitionBlocked,
)
from deeper_dive.storage.workspace import WorkspaceManager


def _composition(tmp_path: Path) -> ProductionComposition:
    return ProductionComposition.build(
        service=DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    )


def test_wizard_context_references_production_composition_and_ids_only(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    state = WizardState(WizardKind.NEW_DEEP_DIVE, "project")
    context = WizardContext(
        composition,
        state,
        project_id="project-id",
        episode_id="episode-id",
        run_id="run-id",
    )

    assert context.composition is composition
    assert context.project_id == "project-id"
    assert context.episode_id == "episode-id"
    assert context.run_id == "run-id"
    assert {field.name for field in fields(WizardContext)} == {
        "composition",
        "state",
        "project_id",
        "episode_id",
        "run_id",
    }


def test_wizard_state_round_trip_contains_only_ui_navigation_metadata() -> None:
    state = WizardState(
        WizardKind.FIRST_RUN,
        "ai-provider",
        setup_mode=SetupMode.QUICK,
    )

    record = state.to_record()

    assert record == {
        "schema_version": 1,
        "kind": "first-run",
        "current_step": "ai-provider",
        "setup_mode": "quick",
    }
    assert WizardState.from_record(record) == state


@pytest.mark.parametrize(
    "forbidden_field",
    ("provider_config", "source_data", "host", "episode_config", "plan", "run", "export"),
)
def test_wizard_state_rejects_business_entity_fields(forbidden_field: str) -> None:
    record: dict[str, object] = {
        "schema_version": 1,
        "kind": "new-deep-dive",
        "current_step": "project",
        "setup_mode": None,
        forbidden_field: {},
    }

    with pytest.raises(ValueError, match="unsupported fields"):
        WizardState.from_record(record)


def test_first_run_and_new_deep_dive_have_stable_shared_step_models() -> None:
    assert [step.key for step in FIRST_RUN_STEPS] == [
        "welcome",
        "system-check",
        "ai-provider",
        "provider-config",
        "model-test",
        "speech",
        "voice-defaults",
        "ready",
    ]
    assert [step.key for step in NEW_DEEP_DIVE_STEPS] == [
        "project",
        "sources",
        "research",
        "hosts",
        "episode",
        "plan",
        "preflight",
    ]


def test_navigation_progress_is_derived_not_stored() -> None:
    complete = {"project": True, "sources": False, "research": False}
    state = WizardState(WizardKind.NEW_DEEP_DIVE, "sources")
    navigator = WizardNavigator(state, lambda key: complete.get(key, False))

    progress = navigator.progress()

    assert progress[0].visual_state is WizardStepVisualState.COMPLETE
    assert progress[1].visual_state is WizardStepVisualState.CURRENT
    assert progress[2].visual_state is WizardStepVisualState.UPCOMING
    assert progress[0].text_marker == "✓"
    assert progress[1].text_marker == "▶"

    with pytest.raises(WizardTransitionBlocked):
        navigator.continue_forward()

    complete["sources"] = True
    assert navigator.continue_forward().current_step == "research"


def test_resume_falls_back_to_earliest_invalid_production_prerequisite() -> None:
    complete = {
        "project": True,
        "sources": False,
        "research": True,
        "hosts": True,
    }
    state = WizardState(WizardKind.NEW_DEEP_DIVE, "episode")
    navigator = WizardNavigator(state, lambda key: complete.get(key, False))

    recovered = navigator.recovered_state()

    assert recovered.current_step == "sources"


def test_resume_preserves_later_location_when_prerequisites_still_valid() -> None:
    complete = {step.key: True for step in NEW_DEEP_DIVE_STEPS}
    state = WizardState(WizardKind.NEW_DEEP_DIVE, "plan")

    recovered = WizardNavigator(state, complete.__getitem__).recovered_state()

    assert recovered.current_step == "plan"
