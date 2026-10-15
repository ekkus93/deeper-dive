"""FPR-06: no second run while any run for the episode is still active."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Barrier

import pytest
from test_generation_start import _episode

from deeper_dive.generation_start import select_or_create_generation_run
from deeper_dive.storage.episode_errors import GenerationRunStillStopping
from deeper_dive.storage.run_repositories import GenerationRunRecord


def _count(service, project_id: str, episode_id: str) -> int:
    with service.hosts(project_id).database.connection() as db:
        return int(
            db.execute(
                "SELECT COUNT(*) FROM generation_runs WHERE episode_id=?", (episode_id,)
            ).fetchone()[0]
        )


def _seed(service, project_id: str, episode_id: str, state: str, **flags) -> GenerationRunRecord:  # type: ignore[no-untyped-def]
    run = GenerationRunRecord(
        f"seed-{state}-{_count(service, project_id, episode_id)}",
        episode_id,
        "sources",
        state,
        "2026-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
        **flags,
    )
    service.runs(project_id).create(run)
    return run


@pytest.mark.parametrize("state", ["pending", "running", "paused"])
def test_cancel_requested_active_run_blocks_a_new_run(tmp_path: Path, state: str) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    run = _seed(service, project_id, episode_id, state, cancel_requested=True)

    with pytest.raises(GenerationRunStillStopping, match="still stopping"):
        select_or_create_generation_run(service, project_id, episode_id)
    assert _count(service, project_id, episode_id) == 1

    # Once the old run reaches a terminal state a new explicit start works.
    service.runs(project_id).update(replace(run, state="cancelled"))
    result = select_or_create_generation_run(service, project_id, episode_id)
    assert result.created
    assert _count(service, project_id, episode_id) == 2


def test_an_older_active_run_behind_a_newer_terminal_run_is_still_found(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    old = _seed(service, project_id, episode_id, "running")
    service.runs(project_id).update(replace(old, modified_at="2026-01-01T00:00:01Z"))
    _seed(service, project_id, episode_id, "failed")
    # The failed run is the latest by id/modified order only if it sorts last.
    with service.hosts(project_id).database.transaction() as db:
        db.execute(
            "UPDATE generation_runs SET modified_at='2026-01-02T00:00:00Z' WHERE state='failed'"
        )

    result = select_or_create_generation_run(service, project_id, episode_id)
    assert not result.created
    assert result.run.id == old.id
    assert _count(service, project_id, episode_id) == 2


def test_concurrent_starts_with_a_stopping_run_create_nothing(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    _seed(service, project_id, episode_id, "running", cancel_requested=True)
    workers = 6
    barrier = Barrier(workers)

    def start() -> str:
        barrier.wait(5)
        try:
            select_or_create_generation_run(service, project_id, episode_id)
        except GenerationRunStillStopping:
            return "refused"
        return "created"

    with ThreadPoolExecutor(workers) as pool:
        outcomes = list(pool.map(lambda _: start(), range(workers)))
    assert outcomes == ["refused"] * workers
    assert _count(service, project_id, episode_id) == 1


def test_start_refuses_an_episode_edited_after_preflight(tmp_path: Path) -> None:
    """FPR-18: the edit-after-preflight window, exercised through ``start()`` itself."""

    from types import SimpleNamespace

    from deeper_dive.episode_config import EpisodeConfigurationConflict
    from deeper_dive.generation_start import GenerationStartService

    service, project_id, episode_id = _episode(tmp_path)
    starter = GenerationStartService(SimpleNamespace(service=service))  # type: ignore[arg-type]

    def preflight_then_edit(_project_id: str, _episode_id: str):  # type: ignore[no-untyped-def]
        with service.hosts(project_id).database.transaction() as db:
            db.execute(
                "UPDATE episodes SET config_json=? WHERE id=?",
                ('{"edited_after_preflight": true}', episode_id),
            )
        return SimpleNamespace(require_ready=lambda: None, issues=(), estimate=None, routes=())

    starter.preflight = preflight_then_edit  # type: ignore[method-assign]

    with pytest.raises(EpisodeConfigurationConflict):
        starter.start(project_id, episode_id)
    assert _count(service, project_id, episode_id) == 0
