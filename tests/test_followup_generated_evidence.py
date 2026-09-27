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
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import (
    EpisodePlanRecord,
    HostEpisodeRepository,
    SegmentPlanRecord,
)
from deeper_dive.storage.repositories import CorpusRepository, SourceChunkRecord, SourceRecord
from deeper_dive.user_config import ProviderConfig, UserConfig, UserConfigStore


class _BadEvidenceTurnProvider:
    def __init__(self, evidence_id: str = "chunk-outside-scope") -> None:
        self.evidence_id = evidence_id

    def generate_turn(self, decision: DirectorDecision) -> dict[str, object]:
        return {
            "speaker_id": decision.speaker_id,
            "text": "This turn attempts to cite outside the supplied evidence scope.",
            "evidence_ids": [self.evidence_id],
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


def test_episode_evidence_ids_filter_cross_project_plan_evidence(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    project_id, episode_id = _episode_with_evidence_plan(composition)
    database = composition.database_for_project(project_id)
    _add_foreign_project_chunk(composition, "chunk-cross-project")
    _set_plan_evidence(database, "plan-r3", "segment-r3", ("chunk-r3", "chunk-cross-project"))

    scoped_evidence = _episode_evidence_ids(database, episode_id)

    assert scoped_evidence == ("chunk-r3",)
    decision = DirectorDecision(
        speaker_id=HostEpisodeRepository(database).list_episode_host_ids(episode_id)[0],
        intent="Exercise cross-project evidence isolation",
        evidence_ids=scoped_evidence,
    )
    with pytest.raises(ValueError, match="outside director scope"):
        HostTurnService(database, _BadEvidenceTurnProvider("chunk-cross-project")).generate(
            "run-r3-cross-project-negative",
            episode_id,
            decision,
        )


def test_episode_evidence_ids_do_not_leak_other_episode_plan(tmp_path: Path) -> None:
    composition = _composition(tmp_path)
    project_id, episode_id = _episode_with_evidence_plan(composition)
    database = composition.database_for_project(project_id)
    host_id = HostEpisodeRepository(database).list_episode_host_ids(episode_id)[0]
    other_episode_id = _add_episode_with_plan(
        composition,
        project_id,
        host_id,
        chunk_id="chunk-other-episode",
        source_id="source-other-episode",
        plan_id="plan-other-episode",
        segment_id="segment-other-episode",
    )

    scoped_evidence = _episode_evidence_ids(database, episode_id)

    assert scoped_evidence == ("chunk-r3",)
    assert _episode_evidence_ids(database, other_episode_id) == ("chunk-other-episode",)
    decision = DirectorDecision(
        speaker_id=host_id,
        intent="Exercise cross-episode evidence isolation",
        evidence_ids=scoped_evidence,
    )
    with pytest.raises(ValueError, match="outside director scope"):
        HostTurnService(database, _BadEvidenceTurnProvider("chunk-other-episode")).generate(
            "run-r3-cross-episode-negative",
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
    _add_indexed_chunk(
        database,
        project.id,
        source_id="source-r3",
        chunk_id="chunk-r3",
        text="Deterministic source passage for generated evidence.",
    )
    _save_plan(
        database,
        episode.id,
        plan_id="plan-r3",
        segment_id="segment-r3",
        evidence_ids=("chunk-r3",),
    )
    return project.id, episode.id


def _add_episode_with_plan(
    composition: ProductionComposition,
    project_id: str,
    host_id: str,
    *,
    chunk_id: str,
    source_id: str,
    plan_id: str,
    segment_id: str,
) -> str:
    database = composition.database_for_project(project_id)
    _add_indexed_chunk(
        database,
        project_id,
        source_id=source_id,
        chunk_id=chunk_id,
        text=f"Deterministic source passage for {chunk_id}.",
    )
    episode = EpisodeConfigurationService(database).create(
        project_id,
        EpisodeConfiguration(
            title=f"Episode for {chunk_id}",
            focus="Evidence isolation",
            target_duration_seconds=60,
            host_ids=(host_id,),
            research_overrides={"policy": "off"},
        ),
    )
    _save_plan(
        database,
        episode.id,
        plan_id=plan_id,
        segment_id=segment_id,
        evidence_ids=(chunk_id,),
    )
    return episode.id


def _add_indexed_chunk(
    database: Database,
    project_id: str,
    *,
    source_id: str,
    chunk_id: str,
    text: str,
) -> None:
    corpus = CorpusRepository(database)
    corpus.create_source(
        SourceRecord(
            id=source_id,
            project_id=project_id,
            origin="user",
            source_type="text/plain",
            title=f"Source for {chunk_id}",
            imported_at="2026-09-27T00:00:00Z",
            status="indexed",
        )
    )
    corpus.create_chunk(
        SourceChunkRecord(
            id=chunk_id,
            source_id=source_id,
            ordinal=0,
            text=text,
            content_hash=f"hash-{chunk_id}",
            location="line 1",
        )
    )


def _add_foreign_project_chunk(composition: ProductionComposition, chunk_id: str) -> None:
    project = composition.service.create_project("Foreign evidence project")
    database = composition.database_for_project(project.id)
    _add_indexed_chunk(
        database,
        project.id,
        source_id="source-cross-project",
        chunk_id=chunk_id,
        text="This source belongs to another project and must not be supplied.",
    )


def _save_plan(
    database: Database,
    episode_id: str,
    *,
    plan_id: str,
    segment_id: str,
    evidence_ids: tuple[str, ...],
) -> None:
    HostEpisodeRepository(database).save_plan(
        EpisodePlanRecord(
            id=plan_id,
            episode_id=episode_id,
            status="approved",
            plan_json=json.dumps({"segments": [{"evidence_ids": list(evidence_ids)}]}),
            created_at="2026-09-27T00:00:00Z",
            modified_at="2026-09-27T00:00:00Z",
        ),
        [
            SegmentPlanRecord(
                id=segment_id,
                episode_plan_id=plan_id,
                ordinal=0,
                title="Evidence segment",
                purpose="Exercise scoped evidence generation",
                target_duration_seconds=60,
                segment_json=json.dumps({"evidence_ids": list(evidence_ids)}),
            )
        ],
    )


def _set_plan_evidence(
    database: Database,
    plan_id: str,
    segment_id: str,
    evidence_ids: tuple[str, ...],
) -> None:
    payload = json.dumps({"evidence_ids": list(evidence_ids)})
    plan_payload = json.dumps({"segments": [{"evidence_ids": list(evidence_ids)}]})
    with database.transaction() as db:
        db.execute(
            "UPDATE segment_plans SET segment_json=? WHERE id=?",
            (payload, segment_id),
        )
        db.execute(
            "UPDATE episode_plans SET plan_json=? WHERE id=?",
            (plan_payload, plan_id),
        )
