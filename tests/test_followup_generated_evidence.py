from __future__ import annotations

import json
from pathlib import Path

import pytest

from deeper_dive import model_roles
from deeper_dive.composition import ProductionComposition, _episode_evidence_ids
from deeper_dive.director_decision import DirectorDecision
from deeper_dive.episode_config import EpisodeConfiguration, EpisodeConfigurationService
from deeper_dive.episode_library_export import EpisodeLibraryExportService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.hosts import create_host_from_preset
from deeper_dive.provider_factory import ProviderFactory
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, SourceChunkRecord, SourceRecord
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class _BadEvidenceTurnProvider:
    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        return {
            "speaker_id": decision.speaker_id,
            "text": "This turn attempts to cite outside the supplied evidence scope.",
            "evidence_ids": ["chunk-outside-scope"],
        }


def test_provider_backed_generation_uses_plan_evidence_and_exports_source_passages(
    tmp_path: Path,
) -> None:
    composition = _composition(tmp_path)
    project_id, episode_id = _episode_with_evidence_plan(composition)

    run = composition.create_generation_run(project_id, episode_id)
    completed = composition.run_generation(project_id, run.id).run

    database = composition.database_for_project(project_id)
    turns = HostTurnService(database).list_turns(episode_id)
    assert completed.state == "completed"
    assert _episode_evidence_ids(database, episode_id) == ("chunk-r3",)
    assert len(turns) == 1
    assert turns[0].evidence_ids == ("chunk-r3",)

    episode = HostEpisodeRepository(database).get_episode(episode_id)
    assert episode is not None
    exported = EpisodeLibraryExportService(composition.service.workspaces).export(
        project_id,
        episode,
        completed,
    )
    transcript = exported.transcript.read_text(encoding="utf-8")
    assert "Citations: chunk-r3" in transcript
    assert "### Source passages" in transcript
    assert "Deterministic source passage for generated evidence." in transcript


def test_generated_turn_rejects_evidence_outside_director_scope(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    project_id, episode_id = _episode_with_evidence_plan(composition)
    database = composition.database_for_project(project_id)
    decision = DirectorDecision(
        speaker_id=HostEpisodeRepository(database).list_episode_host_ids(episode_id)[0],
        intent="Exercise evidence scope validation",
        evidence_ids=("chunk-r3",),
    )

    with pytest.raises(ValueError, match="outside director scope"):
        HostTurnService(database, _BadEvidenceTurnProvider()).generate(
            "run-r3-negative",
            episode_id,
            decision,
        )


def _composition(tmp_path: Path) -> ProductionComposition:
    data_dir = tmp_path / "data"
    UserConfigStore(data_dir / "config.json").save(
        UserConfig(
            providers={
                "dialogue": ProviderConfig(provider_type="fake", default_model="fake-v1"),
                "speech": ProviderConfig(provider_type="fake-tts"),
            },
            defaults={role.value: "dialogue:fake-v1" for role in model_roles.ModelRole},
        )
    )
    return ProductionComposition.build(
        data_dir,
        provider_factory=ProviderFactory(environ={}),
    )


def _episode_with_evidence_plan(composition: ProductionComposition) -> tuple[str, str]:
    project = composition.service.create_project("R3 generated evidence")
    host = create_host_from_preset("curious_explainer", project.id)
    host.tts_provider = "speech"
    host.tts_voice = "voice-a"
    composition.service.hosts(project.id).create_host(host.to_record())
    episode = EpisodeConfigurationService(composition.database_for_project(project.id)).create(
        project.id,
        EpisodeConfiguration(
            title="Generated evidence episode",
            focus="Evidence scoped generation",
            target_duration_seconds=60,
            host_ids=(host.id,),
            research_overrides={"policy": "off"},
        ),
    )
    database = composition.database_for_project(project.id)
    corpus = CorpusRepository(database)
    corpus.create_source(
        SourceRecord(
            id="source-r3",
            project_id=project.id,
            origin="user",
            source_type="text/plain",
            title="R3 source",
            imported_at="2026-09-27T00:00:00Z",
            status="indexed",
        )
    )
    corpus.create_chunk(
        SourceChunkRecord(
            id="chunk-r3",
            source_id="source-r3",
            ordinal=0,
            text="Deterministic source passage for generated evidence.",
            content_hash="hash-r3",
            location="line 1",
        )
    )
    HostEpisodeRepository(database).save_plan(
        EpisodePlanRecord(
            id="plan-r3",
            episode_id=episode.id,
            status="approved",
            plan_json=json.dumps({"segments": [{"evidence_ids": ["chunk-r3"]}]}),
            created_at="2026-09-27T00:00:00Z",
            modified_at="2026-09-27T00:00:00Z",
        ),
        [
            SegmentPlanRecord(
                id="segment-r3",
                episode_plan_id="plan-r3",
                ordinal=0,
                title="Evidence segment",
                purpose="Exercise scoped evidence generation",
                target_duration_seconds=60,
                segment_json=json.dumps({"evidence_ids": ["chunk-r3"]}),
            )
        ],
    )
    return project.id, episode.id
