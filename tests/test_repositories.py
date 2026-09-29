from pathlib import Path

from deeper_dive.storage.database import Database
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)


def project() -> ProjectRecord:
    return ProjectRecord("p1", "Project", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")


def source(origin: str = "user") -> SourceRecord:
    return SourceRecord("s1", "p1", origin, "text", "Source", "2026-01-01T00:00:00Z")


def test_project_source_and_chunk_survive_restart(tmp_path: Path) -> None:
    path = tmp_path / "project.db"
    repo = CorpusRepository(Database(path))
    repo.create_project(project())
    repo.create_source(source("supplemental"))
    repo.create_chunk(SourceChunkRecord("c1", "s1", 0, "evidence", "hash", "page 2"))

    reopened = CorpusRepository(Database(path))
    assert reopened.get_project("p1") == project()
    assert reopened.get_source("s1") == source("supplemental")
    assert reopened.list_chunks("s1")[0].location == "page 2"


def test_crud_and_origin_round_trip(tmp_path: Path) -> None:
    repo = CorpusRepository(Database(tmp_path / "db.sqlite"))
    repo.create_project(project())
    repo.create_source(source())
    assert repo.list_projects() == [project()]
    assert repo.list_sources("p1")[0].origin == "user"

    updated = ProjectRecord(
        "p1",
        "Renamed",
        project().created_at,
        "2026-01-02T00:00:00Z",
        "notes",
    )
    repo.update_project(updated)
    assert repo.get_project("p1") == updated

    updated_source = SourceRecord(
        "s1",
        "p1",
        "user",
        "text",
        "Updated",
        source().imported_at,
        included=False,
        status="parsed",
    )
    repo.update_source(updated_source)
    assert repo.get_source("s1") == updated_source
    repo.delete_source("s1")
    assert repo.get_source("s1") is None


def test_foreign_key_cascade_deletes_sources_and_chunks(tmp_path: Path) -> None:
    repo = CorpusRepository(Database(tmp_path / "db.sqlite"))
    repo.create_project(project())
    repo.create_source(source())
    repo.create_chunk(SourceChunkRecord("c1", "s1", 0, "text", "hash"))
    repo.delete_project("p1")
    assert repo.get_source("s1") is None
    assert repo.list_chunks("s1") == []


def test_list_indexed_chunk_ids_uses_project_source_status_and_inclusion(tmp_path: Path) -> None:
    repo = CorpusRepository(Database(tmp_path / "db.sqlite"))
    repo.create_project(project())
    repo.create_project(
        ProjectRecord("p2", "Other", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    )
    repo.create_source(
        SourceRecord(
            "s-indexed",
            "p1",
            "user",
            "text",
            "Indexed",
            "2026-01-01T00:00:00Z",
            included=True,
            status="indexed",
        )
    )
    repo.create_source(
        SourceRecord(
            "s-excluded",
            "p1",
            "user",
            "text",
            "Excluded",
            "2026-01-02T00:00:00Z",
            included=False,
            status="indexed",
        )
    )
    repo.create_source(
        SourceRecord(
            "s-pending",
            "p1",
            "user",
            "text",
            "Pending",
            "2026-01-03T00:00:00Z",
            included=True,
            status="parsed",
        )
    )
    repo.create_source(
        SourceRecord(
            "s-other-project",
            "p2",
            "user",
            "text",
            "Other project",
            "2026-01-04T00:00:00Z",
            included=True,
            status="indexed",
        )
    )
    repo.create_chunk(SourceChunkRecord("c2", "s-indexed", 1, "second", "hash-2"))
    repo.create_chunk(SourceChunkRecord("c1", "s-indexed", 0, "first", "hash-1"))
    repo.create_chunk(SourceChunkRecord("excluded", "s-excluded", 0, "excluded", "hash-3"))
    repo.create_chunk(SourceChunkRecord("pending", "s-pending", 0, "pending", "hash-4"))
    repo.create_chunk(SourceChunkRecord("other", "s-other-project", 0, "other", "hash-5"))

    assert repo.list_indexed_chunk_ids("p1") == ("c1", "c2")
