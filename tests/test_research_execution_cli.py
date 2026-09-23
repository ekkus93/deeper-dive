from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive.cli import main
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _json_call(args: list[str], capsys: pytest.CaptureFixture[str]) -> object:
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)


def _configure_fake_corpus_analysis(data_dir: Path) -> None:
    provider = ProviderConfig(provider_type="fake", default_model="fake-v1")
    config = UserConfig(
        providers={"researcher": provider},
        defaults={"corpus_analysis": "researcher:fake-v1"},
    )
    UserConfigStore(data_dir / "config.json").save(config)


def _project_with_gap(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[list[str], str, str]:
    _configure_fake_corpus_analysis(tmp_path)
    source = tmp_path / "source.md"
    source.write_text(
        "# Source\n\nA deterministic corpus that needs corroborating context.\n",
        encoding="utf-8",
    )
    base = ["--data-dir", str(tmp_path), "--json"]
    project = _json_call([*base, "project", "create", "Research CLI"], capsys)
    project_id = str(project["id"])
    _json_call([*base, "source", "add", project_id, str(source)], capsys)
    gaps = _json_call([*base, "research", "analyze", project_id], capsys)
    assert isinstance(gaps, list)
    assert gaps
    return base, project_id, str(gaps[0]["id"])


def test_research_run_selected_gap_persists_candidate_outcomes_without_live_network(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base, project_id, gap_id = _project_with_gap(tmp_path, capsys)

    outcomes = _json_call([*base, "research", "run", project_id, gap_id], capsys)

    assert isinstance(outcomes, list)
    assert len(outcomes) == 1
    assert outcomes[0]["project_id"] == project_id
    assert outcomes[0]["gap_id"] == gap_id
    assert outcomes[0]["origin"] == "supplemental"
    assert outcomes[0]["url"].startswith("deeper-dive://supplemental-research/")
    assert outcomes[0]["accepted"] is True
    listed = _json_call([*base, "research", "outcomes", project_id], capsys)
    assert listed == outcomes


def test_research_run_all_skips_ignored_gaps_and_requires_selection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base, project_id, gap_id = _project_with_gap(tmp_path, capsys)

    ignored = _json_call([*base, "research", "ignore", project_id, gap_id], capsys)
    assert ignored == {"id": gap_id, "status": "ignored"}
    outcomes = _json_call([*base, "research", "run", project_id, "--all"], capsys)
    assert outcomes == []
    assert main([*base, "research", "run", project_id]) == 2
    captured = capsys.readouterr()
    assert "research run requires one or more gap IDs or --all" in captured.err
