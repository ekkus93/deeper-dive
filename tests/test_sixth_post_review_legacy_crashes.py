"""6PR-03: Episode Library and Generate survive a database error; the guard sweep sees them."""

from __future__ import annotations

import ast
import asyncio
import sqlite3
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.episode_library_screen import EpisodeLibraryController, EpisodeLibraryScreen
from deeper_dive.preflight_screen import PreflightController, PreflightScreen
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp

SRC = Path(__file__).resolve().parent.parent / "src" / "deeper_dive"
LOCKED = sqlite3.OperationalError("database is locked")


def _status(screen) -> str:  # type: ignore[no-untyped-def]
    return str(screen.query_one("#screen-status", Static).render())


def _app_with_episode(tmp_path: Path):  # type: ignore[no-untyped-def]
    service = DeeperDiveService(WorkspaceManager(tmp_path / "data"))
    project = service.create_project("P")
    episode = service.quick_deep_dive(project.id)
    return service, project, episode, DeeperDiveApp(service)


def test_navigating_to_the_library_survives_a_locked_database(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, _episode, app = _app_with_episode(tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            with patch.object(EpisodeLibraryController, "items", side_effect=LOCKED):
                app.action_navigate("library")
                await pilot.pause()
                await pilot.pause()
                assert app.is_running
                assert isinstance(app.screen, EpisodeLibraryScreen)
                assert "could not refresh" in _status(app.screen)

    asyncio.run(run())


def _library(app, pilot):  # type: ignore[no-untyped-def]
    app.action_navigate("library")
    return pilot.pause()


def test_library_duplicate_and_delete_survive_a_locked_database(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, episode, app = _app_with_episode(tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            await _library(app, pilot)
            screen = app.screen
            assert isinstance(screen, EpisodeLibraryScreen)
            assert screen.selected_episode_id == episode.id

            with patch.object(EpisodeLibraryController, "duplicate", side_effect=LOCKED):
                screen.action_duplicate_selected()
            assert app.is_running and "Not duplicated" in _status(screen)

            screen.action_request_delete()
            with patch.object(EpisodeLibraryController, "delete", side_effect=LOCKED):
                screen.action_confirm_delete()
            assert app.is_running and "Not deleted" in _status(screen)

    asyncio.run(run())


def test_library_duplicate_that_succeeded_is_not_reported_as_failed(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, _episode, app = _app_with_episode(tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            await _library(app, pilot)
            screen = app.screen
            assert isinstance(screen, EpisodeLibraryScreen)
            real_items = EpisodeLibraryController.items
            calls = {"n": 0}

            def flaky(app_):  # type: ignore[no-untyped-def]
                # _selected() inside duplicate's first lookup works; the refresh afterwards fails.
                calls["n"] += 1
                if calls["n"] > 1:
                    raise LOCKED
                return real_items(app_)

            with patch.object(EpisodeLibraryController, "items", side_effect=flaky):
                screen.action_duplicate_selected()
            status = _status(screen)
            assert "Duplicated configuration" in status and "could not refresh" in status
            assert "Not duplicated" not in status
            assert len(EpisodeLibraryController.items(app)) == 2

    asyncio.run(run())


def test_opening_generate_survives_a_failing_preflight(tmp_path: Path) -> None:
    async def run() -> None:
        _service, project, _episode, app = _app_with_episode(tmp_path)
        async with app.run_test(size=(100, 40)) as pilot:
            app.current_project_id = project.id
            with patch.object(PreflightController, "build", side_effect=LOCKED):
                app.action_navigate("generate")
                await pilot.pause()
                await pilot.pause()
            assert app.is_running
            assert isinstance(app.screen, PreflightScreen)
            assert "Preflight unavailable" in _status(app.screen)

    asyncio.run(run())


# --- sweep -------------------------------------------------------------------------------

_MARKERS = ("service", "controller", "repository")
_ENTRY_POINTS = ("on_mount", "on_screen_resume")
_GUARDS = ("report_service_errors", "tolerate_refresh_errors")

# ``Class.method`` -> why it needs no decorator. Whole classes are never exempt.
_REVIEWED = {
    "EpisodePlanScreen.on_mount": "refresh_plan catches _SERVICE_ERRORS itself (FPR-02)",
    "EpisodePlanScreen.action_save_segment": "own _SERVICE_ERRORS handling with a reload hint",
    "EpisodePlanScreen.action_regenerate_segment": "own _SERVICE_ERRORS handling",
    "EpisodePlanScreen.action_regenerate_plan": "own _SERVICE_ERRORS handling",
    "EpisodePlanScreen.action_approve_generate": "own _SERVICE_ERRORS handling",
    "EpisodePlanScreen.action_reload_plan": "6PR-05 guards the reload itself",
    "GenerationMonitorScreen.action_pause": "except Exception with user_status",
    "GenerationMonitorScreen.action_resume": "except Exception with user_status",
    "GenerationMonitorScreen.action_cancel": "except Exception with user_status",
    "GenerationMonitorScreen.action_diagnostics": "except Exception with user_status",
    "ProvidersScreen.action_save": "catches the config errors; config is JSON, not sqlite",
    "ProvidersScreen.action_remove": "catches the config errors; config is JSON, not sqlite",
    "ProvidersScreen.action_confirm_remove": "catches the config errors; config is JSON",
    "ProvidersScreen.action_health": "catches the config errors; config is JSON",
    "ProvidersScreen.action_models": "catches the config errors; config is JSON",
    "ProvidersScreen.action_voices": "catches the config errors; config is JSON",
    "SettingsScreen.action_save_default": "_save catches OSError/TypeError/ValueError (JSON)",
    "SettingsScreen.action_save_model_default": "_save catches OSError/TypeError/ValueError",
    "SettingsScreen.action_save_tts_defaults": "_save catches OSError/TypeError/ValueError",
    "SettingsScreen.action_save_research_defaults": "_save catches OSError/TypeError/ValueError",
    "SettingsScreen.action_save_quick_defaults": "_save catches OSError/TypeError/ValueError",
    "SettingsScreen.action_save_runtime_defaults": "_save catches OSError/TypeError/ValueError",
}


def _is_guarded(function: ast.FunctionDef) -> bool:
    return any(guard in ast.unparse(d) for d in function.decorator_list for guard in _GUARDS)


def _is_screen_class(cls: ast.ClassDef) -> bool:
    return any("Screen" in ast.unparse(base) for base in cls.bases)


def _touches_service(
    methods: dict[str, ast.FunctionDef], name: str, seen: frozenset[str] = frozenset()
) -> bool:
    """Whether a method (or an unguarded ``self.`` helper it calls) reaches a service."""

    function = methods[name]
    if any(marker in ast.unparse(function).lower() for marker in _MARKERS):
        return True
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr in methods
            and node.func.attr not in seen | {name}
            and not _is_guarded(methods[node.func.attr])
            and _touches_service(methods, node.func.attr, seen | {name})
        ):
            return True
    return False


def _unguarded_entry_points(read: Callable[[Path], str] = Path.read_text) -> list[str]:
    found: list[str] = []
    for path in sorted(SRC.glob("*.py")):
        # Guided screens are the wizard framework: their own tests cover them.
        if path.name.startswith("guided_") or path.name == "wizard_shell.py":
            continue
        tree = ast.parse(read(path))
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            if not _is_screen_class(cls):
                continue
            methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
            for name, function in methods.items():
                is_entry = name.startswith("action_") or name in _ENTRY_POINTS
                if not is_entry or _is_guarded(function) or not _touches_service(methods, name):
                    continue
                key = f"{cls.name}.{name}"
                if key not in _REVIEWED:
                    found.append(f"{path.name}:{key}")
    return found


def test_every_legacy_screen_entry_point_is_guarded_or_reviewed() -> None:
    assert _unguarded_entry_points() == []


def test_the_sweep_sees_the_episode_library_and_mount_refreshes() -> None:
    # The discovery is not a fixed file list: strip the library's guards and it must report.
    def unguarded_library(path: Path) -> str:
        text = path.read_text()
        if path.name == "episode_library_screen.py":
            text = text.replace("@report_service_errors", "# ").replace("@tolerate_refresh", "# ")
        return text

    found = _unguarded_entry_points(unguarded_library)
    assert "episode_library_screen.py:EpisodeLibraryScreen.on_mount" in found
    assert "episode_library_screen.py:EpisodeLibraryScreen.action_duplicate_selected" in found
