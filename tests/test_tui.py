from __future__ import annotations

import asyncio

from deeper_dive.tui import GLOBAL_SCREENS, PROJECT_SCREENS, DeeperDiveApp


def test_shell_navigates_all_destinations() -> None:
    asyncio.run(_navigate_all_destinations())


async def _navigate_all_destinations() -> None:
    app = DeeperDiveApp()
    async with app.run_test(size=(100, 30)) as pilot:
        assert app.screen.id == "screen-home"
        for destination in (*GLOBAL_SCREENS[1:], *PROJECT_SCREENS):
            await pilot.press(*_shortcut(destination))
            await pilot.pause()
            assert app.screen.id == f"screen-{destination}"
            assert app.query_one("#screen-status").renderable == "Status: Ready"


def test_shell_runs_at_minimum_terminal_size() -> None:
    asyncio.run(_run_at_minimum_terminal_size())


async def _run_at_minimum_terminal_size() -> None:
    app = DeeperDiveApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("1")
        await pilot.pause()
        assert app.screen.id == "screen-sources"
        await pilot.press("h")
        await pilot.pause()
        assert app.screen.id == "screen-home"


def _shortcut(destination: str) -> tuple[str, ...]:
    return {
        "providers": ("p",),
        "settings": ("s",),
        "help": ("?",),
        "sources": ("1",),
        "research": ("2",),
        "hosts": ("3",),
        "episode": ("4",),
        "generate": ("5",),
        "library": ("6",),
    }[destination]
