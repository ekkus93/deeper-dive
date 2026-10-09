"""Research TUI status must never render authorization credentials."""

from __future__ import annotations

from typing import cast

from deeper_dive.research_screen import ResearchScreen


class FakeStatus:
    def __init__(self) -> None:
        self.text = ""

    def update(self, text: str) -> None:
        self.text = text


class FakeResearchScreen:
    def __init__(self) -> None:
        self.status = FakeStatus()

    def query_one(self, selector: str, _widget_type: object) -> FakeStatus:
        assert selector == "#screen-status"
        return self.status


def test_research_status_redacts_authorization_and_preserves_context() -> None:
    screen = FakeResearchScreen()
    ResearchScreen._status(
        cast(ResearchScreen, screen),
        "Provider request failed: Authorization: Basic research-canary; status=401",
    )
    assert "research-canary" not in screen.status.text
    assert "[REDACTED]" in screen.status.text
    assert "Provider request failed" in screen.status.text
    assert "status=401" in screen.status.text


def test_research_status_preserves_benign_provider_context() -> None:
    screen = FakeResearchScreen()
    ResearchScreen._status(
        cast(ResearchScreen, screen),
        "Model tokenization complete at https://example.test/v1",
    )
    assert "tokenization" in screen.status.text
    assert "https://example.test/v1" in screen.status.text
