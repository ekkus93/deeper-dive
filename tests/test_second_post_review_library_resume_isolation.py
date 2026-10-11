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
