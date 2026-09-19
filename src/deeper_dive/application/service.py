"""Headless application service coordinating persistence and workspace use cases."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from deeper_dive.application.events import ProgressEvent, ProgressSink
from deeper_dive.batch_import import (
    BatchImportPlan,
    canonicalize_url,
    plan_file_imports,
    plan_url_imports,
)
from deeper_dive.chunking import chunk_parse_result
from deeper_dive.domain.clock import Clock, SystemClock, format_timestamp
from deeper_dive.domain.ids import new_chunk_id, new_project_id, new_source_id, parse_project_id
from deeper_dive.html_ingestion import HtmlUrlParser
from deeper_dive.parsing import (
    DocxParser,
    ParseRequest,
    ParseResult,
    PdfParser,
    TextMarkdownParser,
)
from deeper_dive.quick_deep_dive import QuickDeepDiveService
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.storage.repositories import (
    CorpusRepository,
    ProjectRecord,
    SourceChunkRecord,
    SourceRecord,
)
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


@dataclass(frozen=True, slots=True)
class SourceImportSummary:
    """User-presentable source import outcome."""

    plan: BatchImportPlan
    imported: tuple[SourceRecord, ...]


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

    def quick_deep_dive(self, project_id: str) -> EpisodeRecord:
        """Create a normal draft episode using the Quick Deep Dive defaults."""

        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        if repository.get_project(project_id) is None:
            raise KeyError(project_id)
        service = QuickDeepDiveService(Database(workspace.database), clock=self.clock)
        episode = service.create_episode(project_id)
        self._emit("episode.quick_deep_dive", "completed", episode.id)
        return episode

    def add_pasted_source(
        self,
        project_id: str,
        title: str,
        text: str,
        *,
        origin: str = "user",
    ) -> SourceRecord:
        """Persist pasted text and deterministic chunks through the service boundary."""

        if origin not in {"user", "supplemental"}:
            raise ValueError("source origin must be user or supplemental")
        parser = TextMarkdownParser()
        result = parser.parse(ParseRequest(text=text, media_type="text/plain"))
        content_hash = (
            result.metadata.get("content_hash") or hashlib.sha256(text.encode("utf-8")).hexdigest()
        )
        return self._persist_parsed_source(
            project_id,
            origin=origin,
            source_type="pasted-text",
            title=title,
            locator="paste://text",
            content_hash=content_hash,
            result=result,
        )

    def add_file_sources(self, project_id: str, paths: list[Path]) -> SourceImportSummary:
        """Import supported files/directories while surfacing duplicate disposition."""

        repository = self._repository_for_project(project_id)
        plan = plan_file_imports(
            paths,
            self._source_parsers(),
            existing_content_hashes=self._existing_content_hashes(repository, project_id),
        )
        imported: list[SourceRecord] = []
        for candidate in plan.importable:
            path = Path(candidate.locator)
            parser = self._parser_for_path(path)
            if parser is None:
                continue
            result = parser.parse(ParseRequest(path=path))
            imported.append(
                self._persist_parsed_source(
                    project_id,
                    origin="user",
                    source_type=candidate.source_type,
                    title=candidate.title,
                    locator=str(path),
                    content_hash=candidate.content_hash,
                    result=result,
                )
            )
        return SourceImportSummary(plan, tuple(imported))

    def add_url_sources(self, project_id: str, urls: list[str]) -> SourceImportSummary:
        """Import explicit user URLs and expose canonical-URL duplicate disposition."""

        repository = self._repository_for_project(project_id)
        parser = HtmlUrlParser()
        plan = plan_url_imports(
            urls,
            parser,
            existing_canonical_urls=self._existing_canonical_urls(repository, project_id),
        )
        imported: list[SourceRecord] = []
        for candidate in plan.importable:
            result = parser.fetch_user_url(candidate.locator)
            imported.append(
                self._persist_parsed_source(
                    project_id,
                    origin="user",
                    source_type="url",
                    title=candidate.title,
                    locator=candidate.canonical_url or candidate.locator,
                    content_hash=result.metadata.get("content_hash"),
                    result=result,
                )
            )
        return SourceImportSummary(plan, tuple(imported))

    def list_sources(self, project_id: str) -> list[SourceRecord]:
        workspace = self._workspace(project_id)
        return self._corpus(workspace).list_sources(project_id)

    def get_source(self, project_id: str, source_id: str) -> SourceRecord | None:
        workspace = self._workspace(project_id)
        source = self._corpus(workspace).get_source(source_id)
        if source is not None and source.project_id != project_id:
            return None
        return source

    def set_source_included(self, project_id: str, source_id: str, included: bool) -> None:
        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        source = repository.get_source(source_id)
        if source is None or source.project_id != project_id:
            raise KeyError(source_id)
        repository.update_source(replace(source, included=included))

    def delete_source(self, project_id: str, source_id: str) -> None:
        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        source = repository.get_source(source_id)
        if source is None or source.project_id != project_id:
            raise KeyError(source_id)
        repository.delete_source(source_id)

    def list_source_chunks(self, project_id: str, source_id: str) -> list[SourceChunkRecord]:
        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        source = repository.get_source(source_id)
        if source is None or source.project_id != project_id:
            return []
        return repository.list_chunks(source_id)

    def hosts(self, project_id: str) -> HostEpisodeRepository:
        return HostEpisodeRepository(Database(self._workspace(project_id).database))

    def runs(self, project_id: str) -> GenerationRunRepository:
        return GenerationRunRepository(Database(self._workspace(project_id).database))

    def _persist_parsed_source(
        self,
        project_id: str,
        *,
        origin: str,
        source_type: str,
        title: str,
        locator: str,
        content_hash: str | None,
        result: ParseResult,
    ) -> SourceRecord:
        repository = self._repository_for_project(project_id)
        status = self._status_for_parse(result)
        source = SourceRecord(
            id=str(new_source_id()),
            project_id=project_id,
            origin=origin,
            source_type=source_type,
            title=title,
            locator=locator,
            content_hash=content_hash or result.metadata.get("content_hash"),
            imported_at=format_timestamp(self.clock.now()),
            status=status,
        )
        repository.create_source(source)
        for chunk in chunk_parse_result(source.id, origin, result):
            repository.create_chunk(
                SourceChunkRecord(
                    id=str(new_chunk_id()),
                    source_id=source.id,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    location=chunk.location,
                )
            )
        self._emit("source.add", source.status, source.id)
        return source

    def _repository_for_project(self, project_id: str) -> CorpusRepository:
        workspace = self._workspace(project_id)
        repository = self._corpus(workspace)
        if repository.get_project(project_id) is None:
            raise KeyError(project_id)
        return repository

    def _existing_content_hashes(self, repository: CorpusRepository, project_id: str) -> set[str]:
        return {
            source.content_hash
            for source in repository.list_sources(project_id)
            if source.content_hash is not None
        }

    def _existing_canonical_urls(self, repository: CorpusRepository, project_id: str) -> set[str]:
        canonical_urls: set[str] = set()
        for source in repository.list_sources(project_id):
            if source.locator is None:
                continue
            canonical = canonicalize_url(source.locator)
            if canonical is not None:
                canonical_urls.add(canonical)
        return canonical_urls

    @staticmethod
    def _source_parsers() -> list[TextMarkdownParser | PdfParser | DocxParser | HtmlUrlParser]:
        return [TextMarkdownParser(), PdfParser(), DocxParser(), HtmlUrlParser()]

    @classmethod
    def _parser_for_path(
        cls, path: Path
    ) -> TextMarkdownParser | PdfParser | DocxParser | HtmlUrlParser | None:
        request = ParseRequest(path=path)
        for parser in cls._source_parsers():
            if parser.supports(request):
                return parser
        return None

    @staticmethod
    def _status_for_parse(result: ParseResult) -> str:
        if result.has_errors:
            return "error"
        if result.diagnostics:
            return "warning"
        return "parsed"

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
