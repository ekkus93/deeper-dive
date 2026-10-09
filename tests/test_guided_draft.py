"""Wizard-draft security, compatibility, and corruption recovery."""

from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.composition import ProductionComposition
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_readiness import ProductionWizardCompletion
from deeper_dive.guided_workflow import (
    SetupMode,
    WizardContext,
    WizardKind,
    WizardNavigator,
    WizardState,
    WizardStepVisualState,
)
from deeper_dive.storage.workspace import WorkspaceManager


def _setup(tmp_path: Path) -> tuple[ProductionComposition, GuidedDraftStore]:
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    return ProductionComposition.build(service=service), GuidedDraftStore(
        service.workspaces.data_dir
    )


def test_draft_round_trip_preserves_only_navigation_hints_and_durable_ids(
    tmp_path: Path,
) -> None:
    composition, drafts = _setup(tmp_path)
    project = composition.service.create_project("Saved")
    state = WizardState(WizardKind.NEW_DEEP_DIVE, "sources")
    drafts.save(WizardContext(composition, state, project_id=project.id))
    restored = drafts.load(composition, WizardKind.NEW_DEEP_DIVE)
    assert restored is not None
    assert restored.state == state
    assert restored.project_id == project.id
    raw = (tmp_path / "data" / "guided-new-deep-dive-draft.json").read_text()
    assert set(json.loads(raw)) == {"wizard", "project_id", "episode_id", "run_id"}
    assert "Saved" not in raw


def test_setup_mode_round_trips_without_provider_or_credential_data(tmp_path: Path) -> None:
    composition, drafts = _setup(tmp_path)
    state = WizardState(WizardKind.FIRST_RUN, "ai-provider", setup_mode=SetupMode.ADVANCED)
    drafts.save(WizardContext(composition, state))
    restored = drafts.load(composition, WizardKind.FIRST_RUN)
    assert restored is not None
    assert restored.state == state


def test_invalid_or_old_draft_fails_safely(tmp_path: Path) -> None:
    composition, drafts = _setup(tmp_path)
    path = tmp_path / "data" / "guided-new-deep-dive-draft.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    for content in ("{not-json", '{"wizard":{"schema_version":999}}'):
        path.write_text(content)
        assert drafts.load(composition, WizardKind.NEW_DEEP_DIVE) is None
    path.write_text(
        json.dumps(
            {
                "wizard": WizardState(WizardKind.NEW_DEEP_DIVE, "hosts").to_record(),
                "project_id": "not-a-project",
                "episode_id": None,
                "run_id": None,
            }
        )
    )
    restored = drafts.load(composition, WizardKind.NEW_DEEP_DIVE)
    assert restored is not None
    assert restored.state.current_step == "project"
    assert restored.project_id is None


def test_symlink_draft_not_loaded(tmp_path: Path) -> None:
    composition, drafts = _setup(tmp_path)
    drafts.data_dir.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "outside"
    target.write_text("{}")
    (drafts.data_dir / "guided-first-run-draft.json").symlink_to(target)
    assert drafts.load(composition, WizardKind.FIRST_RUN) is None


def test_draft_recovers_to_earliest_missing_production_prerequisite(tmp_path: Path) -> None:
    composition, drafts = _setup(tmp_path)
    project = composition.service.create_project("Incomplete")
    drafts.save(
        WizardContext(
            composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "plan"),
            project_id=project.id,
        )
    )
    recovered = drafts.load(composition, WizardKind.NEW_DEEP_DIVE)
    assert recovered is not None
    assert recovered.project_id == project.id
    # No included/indexed source exists: a stale Plan bookmark must not skip it.
    assert recovered.state.current_step == "sources"


def test_draft_preserves_valid_later_location_when_prerequisites_are_ready(
    tmp_path: Path,
) -> None:
    composition, drafts = _setup(tmp_path)
    project = composition.service.create_project("Working")
    drafts.save(
        WizardContext(
            composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "sources"),
            project_id=project.id,
        )
    )
    resumed = drafts.load(composition, WizardKind.NEW_DEEP_DIVE)
    assert resumed is not None
    assert resumed.state.current_step == "sources"


def test_first_run_draft_recovers_when_provider_readiness_is_invalid(
    tmp_path: Path,
) -> None:
    composition, drafts = _setup(tmp_path)
    drafts.save(
        WizardContext(
            composition,
            WizardState(WizardKind.FIRST_RUN, "ready", setup_mode=SetupMode.ADVANCED),
        )
    )
    resumed = drafts.load(composition, WizardKind.FIRST_RUN)
    assert resumed is not None
    assert resumed.state.current_step == "provider-config"
    assert resumed.state.setup_mode is SetupMode.ADVANCED


def test_ready_setup_invalidated_provider_marks_prerequisite_needs_attention(
    tmp_path: Path,
) -> None:
    """Saved wizard completion must be reevaluated from current production config."""
    composition, drafts = _setup(tmp_path)
    provider = composition.provider_controller
    provider.save_provider(
        "local", "fake", default_model="fake-v1", network_scope="local"
    )
    config = provider.config()
    config.defaults.update(
        {
            "episode_planning": "local:fake-v1",
            "host_generation": "local:fake-v1",
            "directing": "local:fake-v1",
            "verification": "local:fake-v1",
            "speech_setup": "deferred",
            "quick_deep_dive_duration_minutes": "20",
            "research_policy": "useful",
        }
    )
    provider.config_store.save(config)
    state = WizardState(WizardKind.FIRST_RUN, "ready")
    context = WizardContext(composition, state)
    probe = ProductionWizardCompletion(context)
    assert WizardNavigator(state, probe).first_incomplete_prerequisite is None
    drafts.save(context)

    # Remove the configured provider through the same transactional production API.
    provider.remove_provider("local")
    navigator = WizardNavigator(state, probe)
    assert navigator.first_incomplete_prerequisite is not None
    assert navigator.first_incomplete_prerequisite.key == "provider-config"
    states = {entry.key: entry.visual_state for entry in navigator.progress()}
    assert states["provider-config"] is WizardStepVisualState.NEEDS_ATTENTION
    assert states["model-test"] is WizardStepVisualState.NEEDS_ATTENTION
    restored = drafts.load(composition, WizardKind.FIRST_RUN)
    assert restored is not None
    assert restored.state.current_step == "provider-config"
