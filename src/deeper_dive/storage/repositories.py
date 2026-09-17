"""Repository layer for durable project corpus models."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.storage.database import Database


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: str
    name: str
    created_at: str
    modified_at: str
    instructions: str = ""


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: str
    project_id: str
    origin: str
    source_type: str
    title: str
    imported_at: str
    locator: str | None = None
    content_hash: str | None = None
    included: bool = True
    status: str = "pending"


@dataclass(frozen=True, slots=True)
class SourceChunkRecord:
    id: str
    source_id: str
    ordinal: int
    text: str
    content_hash: str
    location: str | None = None


class CorpusRepository:
    """CRUD boundary for projects, sources, and chunks."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.database.initialize()

    def create_project(self, project: ProjectRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                (
                    "INSERT INTO projects(id,name,created_at,modified_at,instructions) "
                    "VALUES (?,?,?,?,?)"
                ),
                (
                    project.id,
                    project.name,
                    project.created_at,
                    project.modified_at,
                    project.instructions,
                ),
            )

    def get_project(self, project_id: str) -> ProjectRecord | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        return None if row is None else ProjectRecord(**dict(row))

    def list_projects(self) -> list[ProjectRecord]:
        with self.database.connection() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY created_at,id").fetchall()
        return [ProjectRecord(**dict(row)) for row in rows]

    def update_project(self, project: ProjectRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE projects SET name=?,modified_at=?,instructions=? WHERE id=?",
                (project.name, project.modified_at, project.instructions, project.id),
            )

    def delete_project(self, project_id: str) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))

    def create_source(self, source: SourceRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                """INSERT INTO sources(
                    id,project_id,origin,source_type,title,locator,content_hash,included,status,imported_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    source.id,
                    source.project_id,
                    source.origin,
                    source.source_type,
                    source.title,
                    source.locator,
                    source.content_hash,
                    int(source.included),
                    source.status,
                    source.imported_at,
                ),
            )

    def get_source(self, source_id: str) -> SourceRecord | None:
        with self.database.connection() as db:
            row = db.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["included"] = bool(data["included"])
        return SourceRecord(**data)

    def list_sources(self, project_id: str) -> list[SourceRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM sources WHERE project_id=? ORDER BY imported_at,id",
                (project_id,),
            ).fetchall()
        result: list[SourceRecord] = []
        for row in rows:
            data = dict(row)
            data["included"] = bool(data["included"])
            result.append(SourceRecord(**data))
        return result

    def update_source(self, source: SourceRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                "UPDATE sources SET title=?,locator=?,content_hash=?,included=?,status=? WHERE id=?",
                (
                    source.title,
                    source.locator,
                    source.content_hash,
                    int(source.included),
                    source.status,
                    source.id,
                ),
            )

    def delete_source(self, source_id: str) -> None:
        with self.database.transaction() as db:
            db.execute("DELETE FROM sources WHERE id=?", (source_id,))

    def create_chunk(self, chunk: SourceChunkRecord) -> None:
        with self.database.transaction() as db:
            db.execute(
                "INSERT INTO source_chunks(id,source_id,ordinal,text,content_hash,location) "
                "VALUES (?,?,?,?,?,?)",
                (
                    chunk.id,
                    chunk.source_id,
                    chunk.ordinal,
                    chunk.text,
                    chunk.content_hash,
                    chunk.location,
                ),
            )

    def list_chunks(self, source_id: str) -> list[SourceChunkRecord]:
        with self.database.connection() as db:
            rows = db.execute(
                "SELECT * FROM source_chunks WHERE source_id=? ORDER BY ordinal",
                (source_id,),
            ).fetchall()
        return [SourceChunkRecord(**dict(row)) for row in rows]
