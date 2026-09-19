from __future__ import annotations

from deeper_dive.tui import DeeperDiveApp, HomeProjectsScreen, SourcesScreen


def _bindings(owner: type[object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for binding in owner.BINDINGS:  # type: ignore[attr-defined]
        key = binding.key
        assert key not in result, f"conflicting shortcut: {key}"
        result[key] = binding.action
        assert binding.description, f"shortcut {key} is not discoverable"
    return result


def test_global_navigation_is_keyboard_accessible_and_discoverable() -> None:
    bindings = _bindings(DeeperDiveApp)
    assert DeeperDiveApp.ENABLE_COMMAND_PALETTE
    assert bindings["ctrl+p"] == "command_palette"
    assert bindings["h"] == "navigate('home')"
    assert bindings["p"] == "navigate('providers')"
    assert bindings["s"] == "navigate('settings')"
    assert bindings["?"] == "navigate('help')"
    assert [bindings[str(index)] for index in range(1, 7)] == [
        "navigate('sources')",
        "navigate('research')",
        "navigate('hosts')",
        "navigate('episode')",
        "navigate('generate')",
        "navigate('library')",
    ]


def test_project_and_source_primary_actions_have_shortcuts() -> None:
    home = _bindings(HomeProjectsScreen)
    assert {"create_project", "open_selected", "rename_selected", "request_delete"} <= set(
        home.values()
    )
    sources = _bindings(SourcesScreen)
    assert {
        "add_paste",
        "add_files",
        "add_urls",
        "toggle_included",
        "delete_selected",
    } <= set(sources.values())
