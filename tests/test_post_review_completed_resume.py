"""Completed guided runs must not survive as stale resumable checkpoints."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from deeper_dive.composition import ProductionComposition
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState


def test_completed_run_invalidates_saved_new_deep_dive_checkpoint(tmp_path: Path) -> None:
    project_id = "project-one"
    episode_id = "episode-one"
    run_id = "run-one"
    service = SimpleNamespace(
        open_project=lambda identity: SimpleNamespace(id=identity),
        hosts=lambda identity: SimpleNamespace(
            get_episode=lambda eid: SimpleNamespace(project_id=identity)
        ),
        runs=lambda identity: SimpleNamespace(
            get=lambda rid: SimpleNamespace(episode_id=episode_id, state="completed")
        ),
    )
    composition = cast(ProductionComposition, SimpleNamespace(service=service))
    store = GuidedDraftStore(tmp_path)
    store.save(
        WizardContext(
            composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "preflight"),
            project_id=project_id,
            episode_id=episode_id,
            run_id=run_id,
        )
    )
    checkpoint = store._path(WizardKind.NEW_DEEP_DIVE)
    assert checkpoint.exists()

    assert store.load(composition, WizardKind.NEW_DEEP_DIVE) is None
    assert not checkpoint.exists()
    assert not store.has_resume(composition)


def test_deleted_project_invalidates_stale_resume_checkpoint(tmp_path: Path) -> None:
    composition = cast(
        ProductionComposition,
        SimpleNamespace(service=SimpleNamespace(open_project=lambda identity: None)),
    )
    store = GuidedDraftStore(tmp_path)
    store.save(
        WizardContext(
            composition,
            WizardState(WizardKind.NEW_DEEP_DIVE, "sources"),
            project_id="deleted-project",
        )
    )
    checkpoint = store._path(WizardKind.NEW_DEEP_DIVE)
    assert checkpoint.exists()
    assert store.load(composition, WizardKind.NEW_DEEP_DIVE) is None
    assert not checkpoint.exists()
    assert not store.has_resume(composition)
