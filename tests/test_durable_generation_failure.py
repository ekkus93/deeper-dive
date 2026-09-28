from __future__ import annotations

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def test_run_generation_persists_assignment_failure_after_run_creation(tmp_path) -> None:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"fake": ProviderConfig(provider_type="fake")},
            defaults={
                "episode_planning": "fake:fake-v1",
                "host_generation": "fake:fake-v1",
            },
        )
    )
    composition = ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )
    project = composition.service.create_project("Durable failure")
    configurations = EpisodeConfigurationService(composition.database_for_project(project.id))
    episode = configurations.create(
        project.id,
        EpisodeConfiguration(title="Episode", target_duration_seconds=1200),
    )
    run = composition.create_generation_run(project.id, episode.id)
    configurations.edit(
        episode.id,
        EpisodeConfiguration(
            title="Episode",
            target_duration_seconds=1200,
            model_overrides={
                "host_generation": {
                    "provider": "",
                    "model": "",
                }
            },
        ),
    )

    with pytest.raises(ValueError, match="invalid model-role configuration"):
        composition.run_generation(project.id, run.id)

    repository = composition.generation_run_repository(project.id)
    persisted = repository.get(run.id)
    assert persisted is not None
    assert persisted.state == "failed"
    assert persisted.failure_code == "generation_execution_failed"
    assert "host_generation" in (persisted.failure_message or "")
    assert repository.list_completed_stages(run.id) == []
