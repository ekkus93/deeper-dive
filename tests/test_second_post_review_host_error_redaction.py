"""Host validation errors must not echo caller-controlled host identifiers."""

from __future__ import annotations

from dataclasses import replace

import pytest

from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord


@pytest.mark.parametrize("operation", ["create", "edit"])
@pytest.mark.parametrize(
    "host_id",
    [
        "missing-host-private-marker",
        "unexpected host with spaces and private marker",
        "https://example.test/path#section-private-marker",
    ],
)
def test_rejected_host_id_never_appears_in_service_error_or_store(
    tmp_path, operation: str, host_id: str
) -> None:
    database = Database(tmp_path / "project.db")
    CorpusRepository(database).create_project(ProjectRecord("project", "Project", "now", "now"))
    service = EpisodeConfigurationService(database)
    original_config = EpisodeConfiguration(title="Original")
    episode = service.create("project", original_config)
    repository = HostEpisodeRepository(database)
    before = repository.get_episode(episode.id)
    assert before is not None

    invalid = replace(original_config, host_ids=(host_id,))
    with pytest.raises(ValueError, match="does not belong to project") as error:
        if operation == "create":
            service.create("project", invalid)
        else:
            service.edit(episode.id, invalid)

    assert host_id not in str(error.value)
    assert "private-marker" not in str(error.value)
    assert repository.get_episode(episode.id) == before
    assert service.load_configuration(episode.id) == original_config
    assert [item.id for item in repository.list_episodes("project")] == [episode.id]
