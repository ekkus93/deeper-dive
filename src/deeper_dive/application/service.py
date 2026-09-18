"""Headless application service coordinating persistence and workspace use cases."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, replace

from deeper_dive.application.events import ProgressEvent, ProgressSink
from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.domain.ids import new_project_id, parse_project_id
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository
from deeper_dive.storage.repositories import CorpusRepository, ProjectRecord, SourceRecord
from deeper_dive.storage.run_repositories import GenerationRunRepository
from deeper_dive.storage.workspace import ProjectWorkspace, WorkspaceManager


@dataclass(frozen=True, slots=True)
class ProjectSummary:
    """Project-list row for UI clients."""

    id: str
    name: str
    modified_at: str
    source_count: int
    episode_count: int
    run_status: str


class DeeperDiveService:
    """Use-case facade; presentation clients depend on this instead of adapters."""

    def __init__(
        self,
        workspace_manager: WorkspaceManager,
        *,
        clock: Clock | None = None,
        progress: ProgressSink | None = None,
    ) -> None:
        self.workspaces = workspace_manager
        self.clock = SystemClock() if clock is None else clock
        self.progress = progress

    def create_project(self, name: str, *, instructions: str = "") -> ProjectRecord:
        project_id = new_project_id()
        workspace = self.workspaces.create_project(project_id)
        timestamp = format_timestamp(self.clock.now())
        project = ProjectRecord(str(project_id), name, timestamp, timestamp, instructions)
        self._corpus(workspace).create_project(project)
        self._emit("project.create", "completed", str(project_id))
        return project

    def open_project(self, project_id: str) -> ProjectRecord | None:
        workspace = self._workspace(project_id)
        return self._corpus(workspace).get_project(project_id)

    def list_projects(self) -> list[ProjectRecord]:
        if not self.workspaces.projects_dir.exists():
            return []
        projects: list[ProjectRecord] = []
        for root in sorted(self.workspaces.projects_dir.iterdir()):
            if not root.is_dir():
                continue
            try:
                project_id = str(parse_project_id(root.name))
            except ValueError:
                continue
            database = root / "project.db"
            if not database.is_file():
                continue
            project = CorpusRepository(Database(database)).get_project(project_id)
            if project is not None:
                projects.append(project)
        return sorted(projects, key=lambda project: (project.created_at, project.id))

    def list_project_summaries(self) -> list[ProjectSummary]:
        """Return project rows with counts and resumability status for the Home screen."""

        return [self._summarize_project(project) for project in self.list_projects()]

    def rename_project(self, project_id: str, name: str) -> ProjectRecord:
        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        project = repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        updated = replace(project, name=name, modified_at=format_timestamp(self.clock.now()))
        repository.update_project(updated)
        return updated

    def delete_project(self, project_id: str) -> None:
        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        if repository.get_project(project_id) is None:
            raise KeyError(project_id)
        repository.delete_project(project_id)
        shutil.rmtree(workspace.root, ignore_errors=True)
        self._emit("project.delete", "completed", project_id)

    def list_sources(self, project_id: str) -> list[SourceRecord]:
        workspace = self._workspace(project_id)
        return self._corpus(workspace).list_sources(project_id)

    def hosts(self, project_id: str) -> HostEpisodeRepository:
        return HostEpisodeRepository(Database(self._workspace(project_id).database))

    def runs(self, project_id: str) -> GenerationRunRepository:
        return GenerationRunRepository(Database(self._workspace(project_id).database))

    def _summarize_project(self, project: ProjectRecord) -> ProjectSummary:
        workspace = self._workspace(project.id)
        database = Database(workspace.database)
        with database.connection() as connection:
            source_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM sources WHERE project_id=?", (project.id,)
                ).fetchone()[0]
            )
            episode_count = int(
                connection.execute(
                    "SELECT COUNT(*) FROM episodes WHERE project_id=?", (project.id,)
                ).fetchone()[0]
            )
            run = connection.execute(
                """SELECT gr.state, gr.pause_requested, gr.cancel_requested
                FROM generation_runs gr
                JOIN episodes e ON e.id = gr.episode_id
                WHERE e.project_id=? AND gr.state NOT IN ('completed','succeeded')
                ORDER BY gr.modified_at DESC, gr.id DESC LIMIT 1""",
                (project.id,),
            ).fetchone()
        status = "ready"
        if run is not None:
            if bool(run["cancel_requested"]):
                status = "cancel requested"
            elif bool(run["pause_requested"]):
                status = "pause requested"
            else:
                status = str(run["state"])
        return ProjectSummary(
            id=project.id,
            name=project.name,
            modified_at=project.modified_at,
            source_count=source_count,
            episode_count=episode_count,
            run_status=status,
        )

    def _workspace(self, project_id: str) -> ProjectWorkspace:
        parsed = parse_project_id(project_id)
        root = self.workspaces.project_root(parsed)
        return ProjectWorkspace(
            project_id=parsed,
            root=root,
            database=root / "project.db",
            sources=root / "sources",
            supplemental=root / "supplemental",
            cache=root / "cache",
            indexes=root / "indexes",
            runs=root / "runs",
            transcripts=root / "transcripts",
            output=root / "output",
        )

    @staticmethod
    def _corpus(workspace: ProjectWorkspace) -> CorpusRepository:
        return CorpusRepository(Database(workspace.database))

    def _emit(self, operation: str, state: str, message: str = "") -> None:
        if self.progress is not None:
            self.progress(ProgressEvent(operation, state, message))
