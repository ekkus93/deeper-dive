"""Episode-library resume must not cross the current project boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.tui import DeeperDiveApp


def test_resume_rejects_cross_project_and_mismatched_run(
    two_project_completed_acceptance: Callable[[], Any],
) -> None:
    completed = two_project_completed_acceptance()
    app = DeeperDiveApp(completed.first.service)
    app.current_project_id = completed.first.project_id
    app.current_episode_id = completed.first.episode_id
    app.current_run_id = completed.first.run_id
    own = EpisodeLibraryController.items(app)[0]
    assert own.run is not None
    mismatched = replace(own, run=replace(own.run, episode_id="other-episode"))
    with pytest.raises(ValueError, match="does not belong to the episode"):
        EpisodeLibraryController.resume(app, mismatched)

    app.current_project_id = completed.second.project_id
    other_item = EpisodeLibraryController.items(app)[0]
    app.current_project_id = completed.first.project_id
    with pytest.raises(ValueError, match="does not belong to the open project"):
        EpisodeLibraryController.resume(app, other_item)
    assert app.current_episode_id == completed.first.episode_id
    assert app.current_run_id == completed.first.run_id


def test_playback_backend_error_preserves_previous_episode_selection(
    two_project_completed_acceptance: Callable[[], Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = two_project_completed_acceptance()
    app = DeeperDiveApp(completed.first.service)
    project_id = completed.first.project_id
    app.current_project_id = project_id
    prior_episode = app.service.quick_deep_dive(project_id)
    app.current_episode_id = prior_episode.id
    app.current_run_id = None
    selected = next(
        item
        for item in EpisodeLibraryController.items(app)
        if item.episode.id == completed.first.episode_id
    )

    def fail_playback(*args: object, **kwargs: object) -> None:
        _ = (args, kwargs)
        raise OSError("synthetic player launch failure")

    monkeypatch.setattr(app.composition.playback_controller, "play", fail_playback)
    with pytest.raises(OSError, match="synthetic player launch failure"):
        EpisodeLibraryController.play(app, selected)
    assert app.current_episode_id == prior_episode.id
    assert app.current_run_id is None
