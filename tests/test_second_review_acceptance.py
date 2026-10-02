from __future__ import annotations

import pytest
from followup_acceptance_fixture import create_ready_followup_fixture, run_followup_fixture

from deeper_dive.cli import _status_payload
from deeper_dive.generation_start import GenerationStartService
from deeper_dive.host_turn import HostTurnService
from deeper_dive.pipeline import PipelineContext
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


@pytest.mark.parametrize("host_assignment", [None, "ghost:unknown", "dialogue:fake-v1"])
def test_completed_conversation_omits_host_resolution_and_preserves_turns(
    tmp_path, host_assignment
):
    ready = create_ready_followup_fixture(tmp_path)
    completed = run_followup_fixture(ready)
    composition = ready.composition
    config = composition.config_store.load()
    defaults = {
        key: value
        for key, value in config.defaults.items()
        if key not in {"host_generation", "directing"}
    }
    if host_assignment is not None:
        defaults["host_generation"] = host_assignment
    composition.config_store.save(config.model_copy(update={"defaults": defaults}))
    before = HostTurnService(ready.database).list_turns(ready.episode_id)
    report = GenerationStartService(composition, ffmpeg_executable=ready.ffmpeg).preflight(
        ready.project_id, ready.episode_id
    )
    assert report.ready
    run = composition.create_generation_run(ready.project_id, ready.episode_id)
    composition.generate_episode_conversation(
        ready.project_id, PipelineContext(run.id, ready.episode_id, "conversation")
    )
    assert HostTurnService(ready.database).list_turns(ready.episode_id) == before
    assert composition.generation_run_repository(ready.project_id).get(completed.run.id)


def test_production_status_explains_informational_boundaries(tmp_path):
    ready = create_ready_followup_fixture(tmp_path)
    events = []
    run = ready.composition.create_generation_run(ready.project_id, ready.episode_id)
    result = ready.composition.run_generation(ready.project_id, run.id, progress=events.append)
    messages = {event.operation: event.message for event in events if event.state == "completed"}
    assert "no ingestion performed" in messages["sources"]
    assert "no research performed" in messages["research"]
    assert "explicit export" in messages["export"]
    episode = HostEpisodeRepository(ready.database).get_episode(ready.episode_id)
    assert "explicit export" in _status_payload(episode, result.run)["stage_description"]
    output = ready.composition.service.workspaces.project_root(ready.project_id) / "output"
    assert not list(output.rglob("manifest.json"))


def test_old_run_cannot_resume_revised_plan_content(tmp_path):
    from deeper_dive.plan_validity import bind_generation_plan_revision

    ready = create_ready_followup_fixture(tmp_path)
    completed = run_followup_fixture(ready)
    before = HostTurnService(ready.database).list_turns(ready.episode_id)
    # Simulate an out-of-band writer or corrupted persisted snapshot. Public
    # planner operations reject this edit; resume must independently reject drift.
    with ready.database.transaction() as db:
        db.execute("UPDATE segment_plans SET title='Tampered' WHERE ordinal=0")
    with pytest.raises(ValueError, match="revision changed"):
        bind_generation_plan_revision(ready.database, completed.run.id, ready.episode_id)
    assert HostTurnService(ready.database).list_turns(ready.episode_id) == before


def test_provider_cli_output_uses_canonical_recursive_redaction(capsys):
    from deeper_dive.command import _output

    _output(
        {
            "health": "Bearer synthetic-cli-secret",
            "voices": [{"id": "voice", "name": "client_secret=synthetic-voice-secret"}],
        },
        True,
    )
    output = capsys.readouterr().out
    assert "synthetic-cli-secret" not in output
    assert "synthetic-voice-secret" not in output
    assert "[REDACTED]" in output and "voice" in output


def test_rejected_revision_preserves_completed_export_and_shared_cache(tmp_path):
    from followup_acceptance_fixture import _AcceptancePlanGenerator

    from deeper_dive.episode_planner import PlannedSegment

    ready = create_ready_followup_fixture(tmp_path)
    completed = run_followup_fixture(ready)
    root = ready.composition.service.workspaces.project_root(ready.project_id)
    artifacts = {
        path: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and path.suffix != ".db"
    }
    planner = ready.composition.planning_service(
        ready.project_id, _AcceptancePlanGenerator(ready.chunk_id)
    )
    for action in [
        lambda: planner.regenerate_plan(ready.episode_id),
        lambda: planner.regenerate_segment(ready.episode_id, 0),
        lambda: planner.edit_segment(ready.episode_id, 0, PlannedSegment("Changed", "", 60)),
    ]:
        with pytest.raises(ValueError, match="frozen"):
            action()
    assert all(path.read_bytes() == content for path, content in artifacts.items())
    assert completed.export.audio.is_file()
