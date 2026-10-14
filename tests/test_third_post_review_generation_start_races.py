"""TPR-12: run creation is one atomic selection and honors the preflight revision."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from test_generation_start import _episode

from deeper_dive.episode_config import EpisodeConfigurationConflict
from deeper_dive.generation_start import select_or_create_generation_run


def _run_count(service, project_id: str, episode_id: str) -> int:
    with service.hosts(project_id).database.connection() as db:
        return int(
            db.execute(
                "SELECT COUNT(*) FROM generation_runs WHERE episode_id=?", (episode_id,)
            ).fetchone()[0]
        )


def test_concurrent_starts_create_exactly_one_run(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    workers = 8
    barrier = Barrier(workers)

    def start() -> tuple[str, bool]:
        barrier.wait(5)
        result = select_or_create_generation_run(service, project_id, episode_id)
        return result.run.id, result.created

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(lambda _: start(), range(workers)))

    assert len({run_id for run_id, _ in results}) == 1
    assert sum(1 for _, created in results if created) == 1
    assert _run_count(service, project_id, episode_id) == 1


def test_edit_after_preflight_refuses_the_start_with_a_typed_conflict(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    repository = service.hosts(project_id)
    preflight_revision = repository.get_episode(episode_id).config_json
    with repository.database.transaction() as db:
        db.execute(
            "UPDATE episodes SET config_json=? WHERE id=?",
            ('{"edited_after_preflight": true}', episode_id),
        )

    with pytest.raises(EpisodeConfigurationConflict):
        select_or_create_generation_run(
            service,
            project_id,
            episode_id,
            expected_episode_config_json=preflight_revision,
        )
    assert _run_count(service, project_id, episode_id) == 0


def test_matching_revision_still_starts(tmp_path: Path) -> None:
    service, project_id, episode_id = _episode(tmp_path)
    revision = service.hosts(project_id).get_episode(episode_id).config_json
    result = select_or_create_generation_run(
        service, project_id, episode_id, expected_episode_config_json=revision
    )
    assert result.created
