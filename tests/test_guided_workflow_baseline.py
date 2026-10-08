"""Assert the archived pre-wizard baseline, not the evolving production UI.

These tests intentionally pin historical evidence in the baseline document.
Tests that inspect current navigation or episode controls belong in the guided
workflow acceptance suite instead of freezing the obsolete interface forever.
"""

from pathlib import Path


BASELINE_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_BASELINE_2026-10-08.md"
)


def test_pre_guided_navigation_baseline_records_flat_subsystem_first_ui() -> None:
    baseline = BASELINE_PATH.read_text(encoding="utf-8")

    assert "global: `home`, `providers`, `settings`, `help`" in baseline
    assert "project: `sources`, `research`, `hosts`, `episode`" in baseline
    assert "implementation subsystems as peer destinations" in baseline


def test_pre_guided_episode_setup_baseline_records_implementation_fields() -> None:
    baseline = BASELINE_PATH.read_text(encoding="utf-8")

    assert "Host IDs in order, comma separated" in baseline
    assert "raw research-policy and citation-behavior strings" in baseline
    assert "raw duration seconds" in baseline
    assert "EpisodeConfigurationService" in baseline


def test_first_run_baseline_records_side_effect_free_probe() -> None:
    baseline = BASELINE_PATH.read_text(encoding="utf-8")

    assert "side-effect-free readiness probe only" in baseline
    assert "does not store a setup-complete flag" in baseline
