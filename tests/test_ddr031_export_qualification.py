from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.retrieval import LexicalIndex
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


def _completed_episode(tmp_path: Path):
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "planner": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={"host_generation": "planner:fake-v1"},
        )
    )
    composition = ProductionComposition.build(
        data_dir, provider_factory=ProviderFactory(environ={})
    )
    project = composition.service.create_project("Library export qualification")
    source_path = tmp_path / "source.txt"
    source_path.write_text("grounded source material", encoding="utf-8")
    summary = composition.service.add_file_sources(project.id, [source_path])
    assert len(summary.imported) == 1
    episode = composition.service.quick_deep_dive(project.id)
    run = composition.create_generation_run(project.id, episode.id)
    result = composition.run_generation(project.id, run.id)
    assert result.run.state == "completed"
    return composition, project, episode, result.run


def test_episode_library_export_writes_complete_episode_specific_artifact_set(
    tmp_path: Path,
) -> None:
    composition, project, episode, run = _completed_episode(tmp_path)
    output_dir = tmp_path / "portable"

    result = EpisodeLibraryExportService(composition.service.workspaces).export(
        project.id, episode, run, output_dir=output_dir
    )

    assert result.paths
    assert all(path.is_file() and path.parent == output_dir for path in result.paths)
    assert episode.id in result.transcript.name
    assert episode.id in result.manifest.name
    assert episode.id in result.metadata.name
    assert result.audio is not None
    assert episode.id in result.audio.name
    assert result.audio.read_bytes().startswith(b"FAKE-WAV")
    assert "Configured fake provider host turn marker" in result.transcript.read_text(\n        encoding="utf-8"\n    )

    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == 1
    assert manifest["sources"][0]["title"] == "source.txt"
    assert manifest["sources"][0]["origin"] == "user"
    assert manifest["sources"][0]["locator"].endswith("source.txt")

    metadata = json.loads(result.metadata.read_text(encoding="utf-8"))
    assert metadata == {
        "episode_id": episode.id,
        "project_id": project.id,
        "run_id": run.id,
        "run_state": "completed",
        "title": episode.title,
    }


def test_episode_library_export_rejects_missing_or_noncompleted_run(tmp_path: Path) -> None:
    composition, project, episode, run = _completed_episode(tmp_path)
    exporter = EpisodeLibraryExportService(composition.service.workspaces)

    with pytest.raises(ValueError, match="no generation run"):
        exporter.export(project.id, episode, None)

    with pytest.raises(ValueError, match="paused.*not exportable"):
        exporter.export(project.id, episode, replace(run, state="paused"))


def test_natural_language_retrieval_query_with_punctuation_is_safe(tmp_path: Path) -> None:
    composition, project, _, _ = _completed_episode(tmp_path)
    index = LexicalIndex(composition.database_for_project(project.id))

    hits = index.search(project.id, "Create a focused deep dive from the indexed project corpus.")

    assert isinstance(hits, list)
