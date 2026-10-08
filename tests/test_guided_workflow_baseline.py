from __future__ import annotations

import inspect

from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.first_run import FirstRunController
from deeper_dive.tui import GLOBAL_SCREENS, PROJECT_SCREENS


def test_pre_guided_navigation_baseline_is_flat_and_subsystem_first() -> None:
    assert GLOBAL_SCREENS == ("home", "providers", "settings", "help")
    assert PROJECT_SCREENS == (
        "sources",
        "research",
        "hosts",
        "episode",
        "generate",
        "library",
    )


def test_pre_guided_episode_setup_baseline_exposes_implementation_fields() -> None:
    source = inspect.getsource(EpisodeSetupScreen.compose)

    assert "Host IDs in order, comma separated" in source
    assert 'id="episode-hosts"' in source
    assert 'id="episode-research-policy"' in source
    assert 'id="episode-citation"' in source
    assert 'placeholder="Target duration seconds"' in source


def test_first_run_baseline_is_a_derived_probe_not_a_completion_flag() -> None:
    source = inspect.getsource(FirstRunController)

    assert "def status" in source
    assert "ffmpeg_available" in source
    assert "kitten_available" in source
    assert "setup_complete" not in source
