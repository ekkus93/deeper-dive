from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from textual.widgets import Input, Static

from deeper_dive.application.service import DeeperDiveService
from deeper_dive.domain.clock import FrozenClock
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tui import DeeperDiveApp, SourcesScreen


def test_sources_screen_imports_directory_and_surfaces_duplicates_and_warnings(
    tmp_path: Path,
) -> None:
    asyncio.run(_sources_directory_import(tmp_path))


async def _sources_directory_import(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "one.txt").write_text("same content\n", encoding="utf-8")
    (corpus / "two.md").write_text("same content\n", encoding="utf-8")
    (corpus / "empty.html").write_text("<script>ignored()</script>", encoding="utf-8")
    service = _service(tmp_path)
    project = service.create_project("Sources")

    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    app.current_project_name = project.name
    async with app.run_test(size=(110, 34)) as pilot:
        app.action_navigate("sources")
        await pilot.pause()
        sources = _sources(app)
        sources.query_one("#source-paths", Input).value = str(corpus)
        sources.action_add_files()
        await pilot.pause()

        assert "one.txt" in _text(sources, "#source-list")
        assert "warning" in _text(sources, "#source-list")
        assert "duplicate_content" in _text(sources, "#screen-status")
        assert "Parsed text" in _text(sources, "#source-text-preview")


def test_sources_screen_imports_urls_and_surfaces_duplicate_urls(tmp_path: Path) -> None:
    asyncio.run(_sources_url_import(tmp_path))


async def _sources_url_import(tmp_path: Path) -> None:
    service = _service(tmp_path)
    project = service.create_project("URLs")
    response = _FakeResponse(
        final_url="https://example.com/article?a=1&b=2",
        content_type="text/html",
        data=b"<main><h1>URL Title</h1><p>URL body</p></main>",
    )

    app = DeeperDiveApp(service)
    app.current_project_id = project.id
    app.current_project_name = project.name
    with patch("deeper_dive.html_ingestion.urlopen", return_value=response):
        async with app.run_test(size=(110, 34)) as pilot:
            app.action_navigate("sources")
            await pilot.pause()
            sources = _sources(app)
            sources.query_one(
                "#source-urls", Input
            ).value = (
                "https://example.com/article?b=2&a=1,https://example.com:443/article?a=1&b=2#frag"
            )
            sources.action_add_urls()
            await pilot.pause()

            assert "example.com/article?a=1&b=2" in _text(sources, "#source-list")
            assert "duplicate_url" in _text(sources, "#screen-status")
            assert "URL body" in _text(sources, "#source-text-preview")


class _FakeHeaders:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type


class _FakeResponse:
    def __init__(self, *, final_url: str, content_type: str, data: bytes) -> None:
        self.headers = _FakeHeaders(content_type)
        self._final_url = final_url
        self._data = data

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def geturl(self) -> str:
        return self._final_url

    def read(self, size: int) -> bytes:
        return self._data[:size]


def _service(tmp_path: Path) -> DeeperDiveService:
    return DeeperDiveService(
        WorkspaceManager(tmp_path / "data"),
        clock=FrozenClock(datetime(2026, 9, 17, 12, 0, 0, tzinfo=UTC)),
    )


def _sources(app: DeeperDiveApp) -> SourcesScreen:
    assert isinstance(app.screen, SourcesScreen)
    return app.screen


def _text(screen: SourcesScreen, selector: str) -> str:
    return str(screen.query_one(selector, Static).render())
