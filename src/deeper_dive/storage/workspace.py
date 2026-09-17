"""Platform-aware data directories and isolated project workspaces."""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.domain.errors import UserError
from deeper_dive.domain.ids import ProjectId, parse_project_id

_PROJECT_SUBDIRECTORIES = (
    "sources",
    "supplemental",
    "cache",
    "indexes",
    "runs",
    "transcripts",
    "output",
)
_COMPONENT_RE = re.compile(r"[^\w.-]+", flags=re.UNICODE)


def default_data_dir(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform-appropriate default application data directory."""

    env = os.environ if environ is None else environ
    platform_name = sys.platform if platform is None else platform
    home_dir = Path.home() if home is None else home

    if platform_name == "win32":
        if env.get("LOCALAPPDATA"):
            root = Path(env["LOCALAPPDATA"])
        else:
            root = home_dir / "AppData" / "Local"
        return root / "deeper-dive"
    if platform_name == "darwin":
        return home_dir / "Library" / "Application Support" / "deeper-dive"

    xdg_data_home = env.get("XDG_DATA_HOME")
    root = Path(xdg_data_home) if xdg_data_home else home_dir / ".local" / "share"
    return root / "deeper-dive"


def sanitize_component(
    value: str,
    *,
    fallback: str = "item",
    max_length: int = 80,
) -> str:
    """Convert display text to a safe single path component.

    Stable persisted objects should still use generated IDs. This helper is for
    user-derived artifact names where a readable component is useful.
    """

    if max_length < 1:
        raise ValueError("max_length must be positive")
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"\s+", "-", normalized)
    normalized = _COMPONENT_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    normalized = normalized.strip(" .-_")
    if normalized in {"", ".", ".."}:
        normalized = fallback
    normalized = normalized[:max_length].rstrip(" .-_")
    return normalized or fallback


def _require_within(base: Path, candidate: Path) -> Path:
    resolved_base = base.resolve(strict=False)
    resolved_candidate = candidate.resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_base)
    except ValueError as exc:
        raise UserError(f"path escapes project workspace: {candidate}") from exc
    return resolved_candidate


@dataclass(frozen=True, slots=True)
class ProjectWorkspace:
    """Resolved paths belonging to one project."""

    project_id: ProjectId
    root: Path
    database: Path
    sources: Path
    supplemental: Path
    cache: Path
    indexes: Path
    runs: Path
    transcripts: Path
    output: Path


class WorkspaceManager:
    """Creates and resolves project-local filesystem state."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        selected = default_data_dir() if data_dir is None else Path(data_dir).expanduser()
        self.data_dir = selected.resolve(strict=False)
        self.projects_dir = self.data_dir / "projects"
        self.models_dir = self.data_dir / "models" / "tts"

    def initialize(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: ProjectId | str) -> Path:
        parsed = parse_project_id(str(project_id))
        return _require_within(self.projects_dir, self.projects_dir / str(parsed))

    def create_project(self, project_id: ProjectId | str) -> ProjectWorkspace:
        self.initialize()
        parsed = parse_project_id(str(project_id))
        root = self.project_root(parsed)
        root.mkdir(parents=False, exist_ok=True)
        for name in _PROJECT_SUBDIRECTORIES:
            (root / name).mkdir(exist_ok=True)
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

    def resolve_project_path(
        self,
        project_id: ProjectId | str,
        relative_path: Path | str,
    ) -> Path:
        """Resolve a project-relative path while rejecting traversal/absolute paths."""

        relative = Path(relative_path)
        if relative.is_absolute():
            raise UserError("project path must be relative")
        root = self.project_root(project_id)
        return _require_within(root, root / relative)
