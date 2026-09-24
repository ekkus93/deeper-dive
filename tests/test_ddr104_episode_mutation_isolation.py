from __future__ import annotations

from pathlib import Path

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.tui import DeeperDiveApp


def test_duplicate_and_delete_do_not_cross_contaminate_episode_state(tmp_path: Path) -> None:
    composition = ProductionComposition.build(
        tmp_path / "data", provider_factory=ProviderFactory(environ={})
    )
    project = composition.service.create_project("Mutation isolation")
    first = composition.service.quick_deep_dive(project.id)
    second = composition.service.quick_deep_dive(project.id)

    app = DeeperDiveApp(composition.service)
    app.current_project_id = project.id

    duplicate = EpisodeLibraryController.duplicate(app, first.id)
    repository = composition.service.hosts(project.id)
    assert duplicate.id not in {first.id, second.id}
    assert duplicate.title.endswith(" Copy")
    assert repository.get_episode(first.id) is not None
    assert repository.get_episode(second.id) is not None
    assert repository.get_episode(duplicate.id) is not None

    second_run = composition.create_generation_run(project.id, second.id)
    EpisodeLibraryController.delete(app, first.id)

    assert repository.get_episode(first.id) is None
    assert repository.get_episode(second.id) is not None
    assert repository.get_episode(duplicate.id) is not None
    assert composition.generation_run_repository(project.id).get(second_run.id) == second_run
