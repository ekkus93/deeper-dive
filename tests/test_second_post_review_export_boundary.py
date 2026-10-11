"""Cross-project and nonterminal-run episode exports must be rejected."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.tui import DeeperDiveApp


def test_foreign_project_library_export_rejected(
    two_project_completed_acceptance: Callable[[], Any],
) -> None:
    fixture = two_project_completed_acceptance()
    app = DeeperDiveApp(fixture.first.service)
    app.current_project_id = fixture.first.project_id
    item = next(
        row
        for row in EpisodeLibraryController.items(app)
        if row.episode.id == fixture.first.episode_id
    )
    app.current_project_id = fixture.second.project_id
    with pytest.raises(ValueError, match="does not belong to the open project"):
        EpisodeLibraryController.export(app, item)


@pytest.mark.parametrize("state", ["pending", "running", "paused", "failed"])
def test_noncompleted_run_cannot_export_or_mutate_historical_artifacts(
    completed_episode_acceptance: Callable[..., Any],
    state: str,
) -> None:
    fixture = completed_episode_acceptance(None)
    app = DeeperDiveApp(fixture.service)
    app.current_project_id = fixture.project_id
    original = next(
        row
        for row in EpisodeLibraryController.items(app)
        if row.episode.id == fixture.episode_id
    )
    assert original.run is not None and original.run.state == "completed"
    transcript = fixture.transcript_path.read_bytes()
    audio = fixture.audio_path.read_bytes()
    runs = fixture.service.runs(fixture.project_id)
    runs.update(replace(original.run, state=state))
    current = next(
        row
        for row in EpisodeLibraryController.items(app)
        if row.episode.id == fixture.episode_id
    )
    assert current.state == state
    with pytest.raises(ValueError, match=f"run state {state} is not exportable"):
        EpisodeLibraryController.export(app, current)
    assert fixture.transcript_path.read_bytes() == transcript
    assert fixture.audio_path.read_bytes() == audio
