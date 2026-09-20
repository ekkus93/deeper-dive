from __future__ import annotations

from deeper_dive.generation_monitor import GenerationMonitorScreen
from deeper_dive.preflight import PreflightEstimate, PreflightIssue, PreflightReport
from deeper_dive.preflight_screen import PreflightScreen


def _report(*issues: PreflightIssue) -> PreflightReport:
    return PreflightReport(
        tuple(issues),
        PreflightEstimate(10.0, 1500, 2000, None),
    )


def test_preflight_errors_and_warnings_have_textual_semantics() -> None:
    text = PreflightScreen._issue_text(
        _report(
            PreflightIssue("blocked", "provider unavailable"),
            PreflightIssue("warning", "source text leaves machine", fatal=False),
        )
    )
    assert "Blockers:" in text
    assert "! provider unavailable [blocked]" in text
    assert "Warnings:" in text
    assert "- source text leaves machine [warning]" in text


def test_generation_progress_is_understandable_without_color() -> None:
    assert GenerationMonitorScreen._progress("TTS", None, None) == "TTS progress: not available"
    assert GenerationMonitorScreen._progress("TTS", 3, None) == "TTS progress: 3 completed unit(s)"
    assert GenerationMonitorScreen._progress("TTS", 3, 5) == "TTS progress: 3/5"


def test_preflight_ready_state_is_explicit_text() -> None:
    text = PreflightScreen._issue_text(_report())
    assert text == "Blockers: none\nWarnings: none"
