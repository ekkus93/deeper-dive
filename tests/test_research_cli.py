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
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={"researcher": ProviderConfig(provider_type="fake", default_model="fake-v1")},
            defaults={"corpus_analysis": "researcher:fake-v1"},
        )
    )


def test_research_analyze_uses_configured_provider_and_persists_gaps(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _configure_fake_corpus_analysis(tmp_path)
    source = tmp_path / "source.md"
    source.write_text("# Source\n\nA deterministic corpus that needs corroborating context.\n", encoding="utf-8")
    base = ["--data-dir", str(tmp_path), "--json"]
    project = _json_call([*base, "project", "create", "Research CLI"], capsys)
    project_id = str(project["id"])
    _json_call([*base, "source", "add", project_id, str(source)], capsys)

    gaps = _json_call(
        [*base, "research", "analyze", project_id, "--focus", "corroboration"], capsys
    )

    assert isinstance(gaps, list)
    assert len(gaps) == 1
    assert gaps[0]["project_id"] == project_id
    assert gaps[0]["category"] == "missing_context"
    assert gaps[0]["source_ids"]
    assert gaps[0]["chunk_ids"]
    listed = _json_call([*base, "research", "gaps", project_id], capsys)
    assert listed == gaps


def test_research_analyze_requires_configured_corpus_analysis_provider(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    base = ["--data-dir", str(tmp_path), "--json"]
    project = _json_call([*base, "project", "create", "Research CLI"], capsys)
    project_id = str(project["id"])

    assert main([*base, "research", "analyze", project_id]) == 2
    captured = capsys.readouterr()
    assert "no provider/model assignment for corpus_analysis" in captured.err
