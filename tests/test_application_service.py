from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from deeper_dive.application.events import ProgressEvent
from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock
from deeper_dive.storage.workspace import WorkspaceManager


def test_headless_service_creates_opens_and_renames_project(tmp_path: Path) -> None:
    events: list[ProgressEvent] = []
    clock = FrozenClock(datetime(2026, 1, 2, 3, 4, tzinfo=UTC))
    service = DeeperDiveService(WorkspaceManager(tmp_path), clock=clock, progress=events.append)

    created = service.create_project("First")
    assert service.open_project(created.id) == created
    renamed = service.rename_project(created.id, "Renamed")
    assert renamed.name == "Renamed"
    assert service.open_project(created.id) == renamed
    assert events == [ProgressEvent("project.create", "completed", created.id)]


def test_application_package_does_not_import_provider_adapters() -> None:
    from deeper_dive.application import service

    names = set(service.__dict__)
    assert not any("provider" in name.lower() or "adapter" in name.lower() for name in names)
