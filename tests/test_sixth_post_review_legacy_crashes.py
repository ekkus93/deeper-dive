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

_SERVICE_WORDS = (
    "service",
    "controller",
    "repository",
    "database",
    "composition",
    "provider_controller",
    "provider_factory",
    "path",
    "read_bytes",
    "write_bytes",
    "read_text",
    "write_text",
)
_GUARDS = ("report_service_errors", "tolerate_refresh_errors")
_REVIEWED: dict[str, str] = {
    "EpisodePlanScreen.action_select_segment": "pure-ui",
}


def _methods(cls: ast.ClassDef) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    return {
        node.name: node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _is_guarded(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        guard in ast.unparse(decorator)
        for decorator in function.decorator_list
        for guard in _GUARDS
    )


def _catches_service_errors(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    names = {node.id for node in ast.walk(handler.type) if isinstance(node, ast.Name)}
    return bool(
        names
        & {
            "Exception",
            "BaseException",
            "OSError",
            "RuntimeError",
            "ValueError",
            "KeyError",
            "IndexError",
            "Error",
            "SERVICE_ERRORS",
            "_SERVICE_ERRORS",
        }
    )


def _inside_catching_try(function: ast.FunctionDef | ast.AsyncFunctionDef, call: ast.Call) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Try) or not any(
            _catches_service_errors(exc) for exc in node.handlers
        ):
            continue
        if any(id(child) == id(call) for statement in node.body for child in ast.walk(statement)):
            return True
    return False


def _is_service_call(call: ast.Call) -> bool:
    name = ast.unparse(call.func).lower()
    if any(
        part in {"provider", "providers", "provider_controller", "provider_factory"}
        for part in name.split(".")
    ):
        return True
    if name in {"json.load", "json.loads"} or name.endswith((".json.load", ".json.loads")):
        return True
    if name in {"open", "path.open", "pathlib.path.open"}:
        return True
    return any(word in name for word in _SERVICE_WORDS)


def _self_calls(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "self"
    ]


def _has_service_path(
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    name: str,
    seen: frozenset[str] = frozenset(),
) -> bool:
    if name not in methods or name in seen:
        return False
    function = methods[name]
    if _is_guarded(function):
        return False
    if any(_is_service_call(call) for call in ast.walk(function) if isinstance(call, ast.Call)):
        return True
    for call in _self_calls(function):
        helper = call.func.attr
        if (
            helper in methods
            and not _is_guarded(methods[helper])
            and _has_service_path(methods, helper, seen | {name})
        ):
            return True
    return False


def _unguarded_paths(
    methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    name: str,
    seen: frozenset[str] = frozenset(),
) -> bool:
    if name not in methods or name in seen:
        return False
    function = methods[name]
    if _is_guarded(function):
        return False
    for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
        if _is_service_call(call) and not _inside_catching_try(function, call):
            return True
        if (
            isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self"
            and call.func.attr in methods
            and not _is_guarded(methods[call.func.attr])
            and _has_service_path(methods, call.func.attr)
            and not _inside_catching_try(function, call)
            and _unguarded_paths(methods, call.func.attr, seen | {name})
        ):
            return True
    return False


def _screen_class_names(trees: list[ast.Module]) -> set[str]:
    classes = [node for tree in trees for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    bases = {
        cls.name: {
            node.id for base in cls.bases for node in ast.walk(base) if isinstance(node, ast.Name)
        }
        for cls in classes
    }

    def inherits_screen(name: str, seen: frozenset[str] = frozenset()) -> bool:
        if name == "Screen":
            return True
        if name in seen:
            return False
        return any(inherits_screen(base, seen | {name}) for base in bases.get(name, ()))

    return {name for name in bases if inherits_screen(name)}


def _review_reason_errors(
    reviewed: dict[str, str],
    classes: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]],
) -> list[str]:
    errors: list[str] = []
    for qualified, reason in reviewed.items():
        class_name, _, method_name = qualified.partition(".")
        methods = classes.get(class_name, {})
        if method_name not in methods:
            errors.append(f"stale review entry: {qualified}")
            continue
        function = methods[method_name]
        if reason == "pure-ui":
            valid = not _has_service_path(methods, method_name)
        elif reason in {"own-try", "json-config"}:
            valid = _has_service_path(methods, method_name) and not _unguarded_paths(
                methods, method_name
            )
            if reason == "json-config":
                valid = valid and any(
                    isinstance(node, ast.Try)
                    and any(
                        {name.id for name in ast.walk(handler.type)}
                        & {"OSError", "TypeError", "ValueError"}
                        for handler in node.handlers
                        if handler.type is not None
                    )
                    for node in ast.walk(function)
                )
        else:
            valid = False
        if not valid:
            errors.append(f"unverified review reason {reason!r}: {qualified}")
    return errors


def _scan_sources(
    read: Callable[[Path], str], paths: list[Path] | None = None
) -> tuple[list[str], dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]]]:
    paths = sorted(SRC.rglob("*.py")) if paths is None else paths
    trees = [ast.parse(read(path)) for path in paths]
    screen_names = _screen_class_names(trees)
    class_nodes = {
        cls.name: cls for tree in trees for cls in ast.walk(tree) if isinstance(cls, ast.ClassDef)
    }
    declared_methods = {name: _methods(cls) for name, cls in class_nodes.items()}
    class_bases = {
        name: {
            node.id for base in cls.bases for node in ast.walk(base) if isinstance(node, ast.Name)
        }
        for name, cls in class_nodes.items()
    }

    def effective_methods(
        name: str, seen: frozenset[str] = frozenset()
    ) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
        if name in seen:
            return {}
        methods: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for base in class_bases.get(name, ()):
            methods.update(effective_methods(base, seen | {name}))
        methods.update(declared_methods.get(name, {}))
        return methods

    classes = {name: effective_methods(name) for name in screen_names}
    found: list[str] = []
    for path, tree in zip(paths, trees, strict=True):
        for cls in (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)):
            if cls.name not in screen_names:
                continue
            methods = classes[cls.name]
            for name, _function in methods.items():
                is_entry = name.startswith(("action_", "on_", "key_", "watch_"))
                if (
                    is_entry
                    and _has_service_path(methods, name)
                    and _unguarded_paths(methods, name)
                ):
                    qualified = f"{cls.name}.{name}"
                    if qualified not in _REVIEWED:
                        found.append(f"{path.name}:{qualified}")
    found.extend(_review_reason_errors(_REVIEWED, classes))
    return found, classes


def _unguarded_entry_points(read: Callable[[Path], str] = Path.read_text) -> list[str]:
    return _scan_sources(read)[0]


def test_every_framework_screen_entry_point_is_guarded_or_verified() -> None:
    assert _unguarded_entry_points() == []


def test_the_sweep_sees_framework_handlers_transitive_refresh_and_inheritance() -> None:
    source = """
from textual.screen import Screen
class Intermediate(Screen):
    pass
class Legacy(Intermediate):
    def action_pause(self):
        self.controller.pause()
    def on_button_pressed(self, event):
        self.database.save()
    def key_p(self):
        self.refresh_status()
    def refresh_status(self):
        self.service.snapshot()
class GenerationMonitorScreen(Screen):
    def action_pause(self): self._run()
    def action_resume(self): self._run()
    def action_cancel(self): self._run()
    def action_diagnostics(self): self._run()
    def _run(self): self.controller.snapshot()
class BaseWithRefresh(Screen):
    def refresh_inherited(self): self.database.read()
class InheritedHandler(BaseWithRefresh):
    def action_inherited(self): self.refresh_inherited()
class ClaimInspectorScreen(Screen):
    def action_repair(self):
        self.controller.repair()
        self.refresh_claims()
    def refresh_claims(self): self.database.read()
class ProvidersScreen(Screen):
    def action_save(self):
        self.provider.save()
        self.refresh_providers()
    def action_confirm_remove(self): self.refresh_providers()
    def refresh_providers(self): self.provider_controller.config()
"""
    found, _ = _scan_sources(lambda _path: source, [Path("legacy.py")])
    finding_set = set(found)
    assert {
        "legacy.py:Legacy.action_pause",
        "legacy.py:Legacy.key_p",
        "legacy.py:Legacy.on_button_pressed",
        "legacy.py:GenerationMonitorScreen.action_pause",
        "legacy.py:GenerationMonitorScreen.action_resume",
        "legacy.py:GenerationMonitorScreen.action_cancel",
        "legacy.py:GenerationMonitorScreen.action_diagnostics",
        "legacy.py:ClaimInspectorScreen.action_repair",
        "legacy.py:ProvidersScreen.action_save",
        "legacy.py:ProvidersScreen.action_confirm_remove",
        "legacy.py:InheritedHandler.action_inherited",
    } <= finding_set


def test_the_sweep_rejects_stripped_guards_and_review_reasons() -> None:
    def unguarded_library(path: Path) -> str:
        text = path.read_text()
        if path.name == "episode_library_screen.py":
            text = text.replace("@report_service_errors", "# ").replace("@tolerate_refresh", "# ")
        return text

    found = _unguarded_entry_points(unguarded_library)
    assert any("EpisodeLibraryScreen.on_mount" in item for item in found)
    invalid_reason = {"EpisodePlanScreen.action_select_segment": ""}

    def source(_path: Path) -> str:
        return """
from textual.screen import Screen
class EpisodePlanScreen(Screen):
    def action_select_segment(self):
        self.query_one('x')
"""

    _errors, classes = _scan_sources(source, [Path("review.py")])
    assert any(
        "unverified review reason" in item
        for item in _review_reason_errors(invalid_reason, classes)
    )
