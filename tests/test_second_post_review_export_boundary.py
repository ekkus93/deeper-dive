"""Cross-project episode exports must not use another project's selection."""

from __future__ import annotations

from collections.abc import Callable
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
        row for row in EpisodeLibraryController.items(app)
        if row.episode.id == fixture.first.episode_id
    )
    app.current_project_id = fixture.second.project_id
    with pytest.raises(ValueError, match="does not belong to the open project"):
        EpisodeLibraryController.export(app, item)
