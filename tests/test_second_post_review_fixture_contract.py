"""Assert the shared second-review fixture exercises real production boundaries."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from deeper_dive.composition import ProductionComposition
from deeper_dive.episode_config import EpisodeConfigurationService
from deeper_dive.episode_library_screen import EpisodeLibraryController
from deeper_dive.guided_draft import GuidedDraftStore
from deeper_dive.guided_workflow import WizardContext, WizardKind, WizardState
from deeper_dive.research_policy import ResearchMode, ResearchPolicyStore
from deeper_dive.storage.database import Database
from deeper_dive.tui import DeeperDiveApp
from deeper_dive.user_config import UserConfigStore


def test_two_project_fixture_contains_indexed_corpora_and_generation_artifacts(
    second_post_review_acceptance: Callable[[], Any],
) -> None:
    fixture = second_post_review_acceptance()
    service = fixture.completed.first.service
    data_dir = service.workspaces.data_dir
    config = UserConfigStore(data_dir / "config.json").load()
    assert config.providers["fake"].provider_type == "fake"
    assert config.providers["speech"].provider_type == "fake-tts"
    assert config.defaults["research_policy"] == "useful"
    assert (data_dir / "config.json").read_bytes() == fixture.config_bytes
    assert len(set(fixture.identity_snapshot)) == len(fixture.identity_snapshot)

    episodes = (fixture.completed.first, fixture.completed.second)
    for current in episodes:
        sources = service.list_sources(current.project_id)
        assert len(sources) == 1
        chunks = service.list_source_chunks(current.project_id, sources[0].id)
        assert chunks and all(chunk.text for chunk in chunks)
        host_ids = service.hosts(current.project_id).list_episode_host_ids(current.episode_id)
        assert len(host_ids) == 2
        policy = ResearchPolicyStore(
            Database(service.workspaces.project_root(current.project_id) / "project.db")
        )
        assert policy.episode(current.project_id, current.episode_id).mode is ResearchMode.USEFUL
        run = service.runs(current.project_id).get(current.run_id)
        assert run is not None and run.state == "completed"
        assert current.turn_ids and len(set(current.turn_ids)) == len(current.turn_ids)
        assert current.transcript_path.read_bytes()
        assert current.audio_path.read_bytes()

    foreign_source_id = service.list_sources(episodes[1].project_id)[0].id
    assert service.get_source(episodes[0].project_id, foreign_source_id) is None

    pending_run = service.runs(fixture.pending_project_id).get(fixture.pending_run_id)
    assert pending_run is not None and pending_run.state == "pending"
    configuration = EpisodeConfigurationService(
        Database(service.workspaces.project_root(fixture.pending_project_id) / "project.db")
    ).load_configuration(fixture.pending_episode_id)
    serialized = json.dumps(
        configuration.snapshot(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert serialized == fixture.pending_config_snapshot


def test_checkpoint_plan_run_and_export_snapshots_survive_restart(
    second_post_review_acceptance: Callable[[], Any],
) -> None:
    fixture = second_post_review_acceptance()
    service = fixture.completed.first.service
    data_dir = service.workspaces.data_dir
    composition = ProductionComposition.build(service=service)
    context = WizardContext(
        composition,
        WizardState(WizardKind.NEW_DEEP_DIVE, "episode"),
        project_id=fixture.pending_project_id,
        episode_id=fixture.pending_episode_id,
        run_id=fixture.pending_run_id,
    )
    checkpoint = GuidedDraftStore(data_dir)
    checkpoint.save(context)
    draft_path = data_dir / "guided-new-deep-dive-draft.json"

    def state_bytes(active: ProductionComposition) -> dict[str, bytes]:
        active_service = active.service
        project_id = fixture.pending_project_id
        episode_id = fixture.pending_episode_id
        database = Database(active_service.workspaces.project_root(project_id) / "project.db")
        config = EpisodeConfigurationService(database).load_configuration(episode_id)
        host_ids = active_service.hosts(project_id).list_episode_host_ids(episode_id)
        run = active_service.runs(project_id).get(fixture.pending_run_id)
        assert run is not None
        with database.connection() as connection:
            plan = connection.execute(
                "SELECT plan_json FROM episode_plans WHERE episode_id=?",
                (episode_id,),
            ).fetchone()
        assert plan is not None
        snapshots: dict[str, bytes] = {
            "config": (data_dir / "config.json").read_bytes(),
            "draft": draft_path.read_bytes(),
            "episode": json.dumps(config.snapshot(), sort_keys=True).encode("utf-8"),
            "host_order": json.dumps(host_ids).encode("utf-8"),
            "plan": str(plan["plan_json"]).encode("utf-8"),
            "run": json.dumps(asdict(run), sort_keys=True).encode("utf-8"),
            "transcript": fixture.completed.first.transcript_path.read_bytes(),
            "audio": fixture.completed.first.audio_path.read_bytes(),
        }
        for index, completed in enumerate(
            (fixture.completed.first, fixture.completed.second), start=1
        ):
            completed_db = Database(
                active_service.workspaces.project_root(completed.project_id) / "project.db"
            )
            completed_config = EpisodeConfigurationService(completed_db).load_configuration(
                completed.episode_id
            )
            completed_hosts = active_service.hosts(completed.project_id).list_episode_host_ids(
                completed.episode_id
            )
            completed_run = active_service.runs(completed.project_id).get(completed.run_id)
            assert completed_run is not None
            with completed_db.connection() as connection:
                completed_plan = connection.execute(
                    "SELECT plan_json FROM episode_plans WHERE episode_id=?",
                    (completed.episode_id,),
                ).fetchone()
            assert completed_plan is not None
            prefix = f"completed-{index}"
            snapshots.update(
                {
                    f"{prefix}-episode": json.dumps(
                        completed_config.snapshot(), sort_keys=True
                    ).encode("utf-8"),
                    f"{prefix}-host-order": json.dumps(completed_hosts).encode("utf-8"),
                    f"{prefix}-plan": str(completed_plan["plan_json"]).encode("utf-8"),
                    f"{prefix}-run": json.dumps(asdict(completed_run), sort_keys=True).encode(
                        "utf-8"
                    ),
                    f"{prefix}-transcript-path": str(completed.transcript_path).encode("utf-8"),
                    f"{prefix}-audio-path": str(completed.audio_path).encode("utf-8"),
                    f"{prefix}-transcript": completed.transcript_path.read_bytes(),
                    f"{prefix}-audio": completed.audio_path.read_bytes(),
                    f"{prefix}-manifest": completed.manifest_path.read_bytes(),
                    f"{prefix}-metadata": completed.metadata_path.read_bytes(),
                }
            )
        return snapshots

    before = state_bytes(composition)
    assert all(before.values())
    assert before["config"] == fixture.config_bytes
    assert b"api_key" not in before["draft"]
    assert b"source_body" not in before["draft"]

    reopened = ProductionComposition.build(data_dir=data_dir)
    loaded = checkpoint.load(reopened, WizardKind.NEW_DEEP_DIVE, recover=False)
    assert loaded is not None
    assert loaded.project_id == fixture.pending_project_id
    assert loaded.episode_id == fixture.pending_episode_id
    assert loaded.run_id == fixture.pending_run_id
    assert state_bytes(reopened) == before

    # Re-enter the real library/export controller after a fresh composition
    # rebuild. Each export must retain its own episode/run identity and bytes.
    for index, completed in enumerate((fixture.completed.first, fixture.completed.second), start=1):
        app = DeeperDiveApp(reopened.service)
        app.current_project_id = completed.project_id
        app.current_episode_id = completed.episode_id
        app.current_run_id = completed.run_id
        item = next(
            row
            for row in EpisodeLibraryController.items(app)
            if row.episode.id == completed.episode_id
        )
        assert item.run is not None and item.run.id == completed.run_id
        exported = EpisodeLibraryController.export(app, item)
        assert exported.audio is not None
        prefix = f"completed-{index}"
        assert exported.transcript.read_bytes() == before[f"{prefix}-transcript"]
        assert exported.audio.read_bytes() == before[f"{prefix}-audio"]
        assert exported.manifest.read_bytes() == before[f"{prefix}-manifest"]
        assert exported.metadata.read_bytes() == before[f"{prefix}-metadata"]
        metadata = json.loads(exported.metadata.read_text(encoding="utf-8"))
        assert metadata["project_id"] == completed.project_id
        assert metadata["episode_id"] == completed.episode_id
        assert metadata["run_id"] == completed.run_id
    assert state_bytes(reopened) == before
