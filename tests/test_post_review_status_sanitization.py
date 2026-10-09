"""Every shared advanced-screen status boundary must redact diagnostic credentials."""

from __future__ import annotations

import pytest

from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.episode_plan_screen import EpisodePlanScreen
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightScreen
from deeper_dive.settings_screen import SettingsScreen
from deeper_dive.transcript_review_screen import TranscriptReviewScreen
from deeper_dive.tui import HomeProjectsScreen, SourcesScreen


class _StatusCapture:
    def __init__(self) -> None:
        self.content: object = ""

    def update(self, content: object) -> None:
        self.content = content


class _StubScreen:
    def __init__(self) -> None:
        self.status = _StatusCapture()

    def query_one(self, selector: str, _widget_type: object) -> _StatusCapture:
        assert selector == "#screen-status"
        return self.status


@pytest.mark.parametrize(
    ("screen", "method"),
    [
        (HomeProjectsScreen, "_set_status"),
        (SourcesScreen, "_set_status"),
        (HostsScreen, "_status"),
        (SettingsScreen, "_status"),
        (EpisodePlanScreen, "_status"),
        (EpisodeSetupScreen, "_status"),
        (EpisodeLibraryScreen, "_status"),
        (PreflightScreen, "_status"),
        (TranscriptReviewScreen, "_status"),
    ],
)
def test_shared_status_boundaries_redact_provider_credentials(
    screen: type[object], method: str
) -> None:
    fake = _StubScreen()
    message = (
        "Authorization: Basic status-basic-canary; "
        "url=https://status-user-canary@service.test/v1?key=status-url-canary"
    )
    getattr(screen, method)(fake, message)
    visible = str(fake.status.content)
    assert "status-basic-canary" not in visible
    assert "status-user-canary" not in visible
    assert "status-url-canary" not in visible
    assert "[REDACTED]" in visible
    assert "Status:" in visible
