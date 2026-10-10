"""Every shared advanced-screen status boundary must redact diagnostic credentials."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from deeper_dive.episode_library_screen import EpisodeLibraryScreen
from deeper_dive.episode_plan_screen import EpisodePlanScreen
from deeper_dive.episode_setup_screen import EpisodeSetupScreen
from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.guided_episode_wizard import GuidedEpisodeWizard
from deeper_dive.guided_first_run import GuidedFirstRunWizard
from deeper_dive.hosts_screen import HostsScreen
from deeper_dive.preflight_screen import PreflightScreen
from deeper_dive.providers_screen import ProvidersScreen
from deeper_dive.research_screen import ResearchScreen
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


_STATUS_BOUNDARIES = (
    (HomeProjectsScreen, "_set_status"),
    (SourcesScreen, "_set_status"),
    (HostsScreen, "_status"),
    (ProvidersScreen, "_status"),
    (SettingsScreen, "_status"),
    (ResearchScreen, "_status"),
    (EpisodePlanScreen, "_status"),
    (EpisodeSetupScreen, "_status"),
    (EpisodeLibraryScreen, "_status"),
    (PreflightScreen, "_status"),
    (TranscriptReviewScreen, "_status"),
    (GenerationMonitorScreen, "_status"),
)


@pytest.mark.parametrize(("screen", "method"), _STATUS_BOUNDARIES)
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


def test_status_surface_inventory_is_explicit() -> None:
    names = {screen.__name__ for screen, _method in _STATUS_BOUNDARIES}
    assert names == {
        "HomeProjectsScreen",
        "SourcesScreen",
        "HostsScreen",
        "ProvidersScreen",
        "SettingsScreen",
        "ResearchScreen",
        "EpisodePlanScreen",
        "EpisodeSetupScreen",
        "EpisodeLibraryScreen",
        "PreflightScreen",
        "TranscriptReviewScreen",
        "GenerationMonitorScreen",
    }


class _WizardStatusStub:
    def __init__(self) -> None:
        self.status = _StatusCapture()
        self._last_form_status = ""
        self._error_details = None

    def query_one(self, selector: str, _widget_type: object) -> _StatusCapture:
        assert selector == "#wizard-status"
        return self.status


@pytest.mark.parametrize("wizard", [GuidedFirstRunWizard, GuidedEpisodeWizard])
def test_guided_status_boundaries_redact_provider_credentials(wizard: type[object]) -> None:
    fake = _WizardStatusStub()
    message = (
        "Authorization: Token guided-token-canary; "
        "url=https://guided-user-canary@service.test/v1?authorization=guided-query-canary"
    )
    wizard.set_status(fake, message)
    visible = str(fake.status.content)
    for canary in ("guided-token-canary", "guided-user-canary", "guided-query-canary"):
        assert canary not in visible
    assert "[REDACTED]" in visible


class _PersistedFailureStub:
    def __init__(self) -> None:
        self.diagnostics = _StatusCapture()

    def _run(self) -> object:
        return SimpleNamespace(
            id="run-canary",
            state="failed",
            stage="planning",
            retry_count=1,
            failure_code="stage_failed",
            failure_message=(
                "Authorization: Digest persisted-failure-canary; "
                "https://persisted-user-canary@service.test/v1?key=persisted-key-canary"
            ),
        )

    def query_one(self, selector: str, _widget_type: object) -> _StatusCapture:
        assert selector == "#diagnostics-summary"
        return self.diagnostics


def test_persisted_generation_failure_diagnostics_redact_canaries() -> None:
    fake = _PersistedFailureStub()
    GenerationMonitorScreen.action_diagnostics(fake)
    visible = str(fake.diagnostics.content)
    for canary in (
        "persisted-failure-canary",
        "persisted-user-canary",
        "persisted-key-canary",
    ):
        assert canary not in visible
    assert "[REDACTED]" in visible
