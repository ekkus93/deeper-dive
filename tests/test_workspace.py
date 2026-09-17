from __future__ import annotations

from pathlib import Path

import pytest

from deeper_dive.domain.errors import UserError
from deeper_dive.domain.ids import new_project_id
from deeper_dive.storage.workspace import WorkspaceManager, default_data_dir, sanitize_component


def test_default_data_dir_uses_xdg_on_linux(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    assert default_data_dir(environ={"XDG_DATA_HOME": str(xdg)}, platform="linux", home=tmp_path) == xdg / "deeper-dive"


def test_default_data_dir_linux_fallback(tmp_path: Path) -> None:
    assert default_data_dir(environ={}, platform="linux", home=tmp_path) == tmp_path / ".local" / "share" / "deeper-dive"


def test_default_data_dir_macos(tmp_path: Path) -> None:
    assert default_data_dir(environ={}, platform="darwin", home=tmp_path) == tmp_path / "Library" / "Application Support" / "deeper-dive"


def test_default_data_dir_windows_uses_localappdata(tmp_path: Path) -> None:
    local = tmp_path / "LocalAppData"
    assert default_data_dir(environ={"LOCALAPPDATA": str(local)}, platform="win32", home=tmp_path) == local / "deeper-dive"


def test_sanitize_component_removes_path_syntax_and_normalizes_whitespace() -> None:
    assert sanitize_component("  ../../My   Episode: 01  ") == "My-Episode-01"
    assert sanitize_component("..") == "item"
    assert sanitize_component("a/b\\c") == "a-b-c"


def test_two_projects_get_isolated_workspace_layouts(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "data")
    first = manager.create_project(new_project_id())
    second = manager.create_project(new_project_id())

    assert first.root != second.root
    assert first.root.parent == second.root.parent == manager.projects_dir
    for workspace in (first, second):
        assert workspace.root.is_dir()
        assert workspace.database == workspace.root / "project.db"
        for directory in (
            workspace.sources,
            workspace.supplemental,
            workspace.cache,
            workspace.indexes,
            workspace.runs,
            workspace.transcripts,
            workspace.output,
        ):
            assert directory.is_dir()
            assert directory.parent == workspace.root


def test_explicit_data_directory_override_is_honored(tmp_path: Path) -> None:
    override = tmp_path / "custom-data"
    manager = WorkspaceManager(override)
    manager.initialize()
    assert manager.data_dir == override.resolve()
    assert manager.projects_dir.is_dir()
    assert manager.models_dir.is_dir()


def test_project_path_rejects_traversal_and_absolute_paths(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "data")
    project_id = new_project_id()
    workspace = manager.create_project(project_id)

    with pytest.raises(UserError, match="escapes project workspace"):
        manager.resolve_project_path(project_id, "../../outside.txt")
    with pytest.raises(UserError, match="must be relative"):
        manager.resolve_project_path(project_id, tmp_path / "outside.txt")

    safe = manager.resolve_project_path(project_id, "output/episode.mp3")
    assert safe == workspace.output / "episode.mp3"


def test_project_root_rejects_noncanonical_or_malicious_ids(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "data")
    with pytest.raises(ValueError):
        manager.project_root("../../escape")
