from __future__ import annotations

import json
import wave

from deeper_dive import deterministic_fixture
from deeper_dive.storage.database import Database
from deeper_dive.storage.workspace import WorkspaceManager


def test_deterministic_fixture_runs_end_to_end_without_network(tmp_path):
    runner = deterministic_fixture.DeterministicFixtureRunner(WorkspaceManager(tmp_path))

    result = runner.run()

    assert result.episode_id == deterministic_fixture.FIXTURE_EPISODE_ID
    assert result.run_id == deterministic_fixture.FIXTURE_RUN_ID
    assert result.executed_stages == deterministic_fixture.DEFAULT_STAGES
    assert result.skipped_stages == ()
    assert result.artifacts.wav.is_file()
    assert result.artifacts.transcript.is_file()
    assert result.artifacts.manifest.is_file()
    assert result.artifacts.metadata.is_file()

    transcript = result.artifacts.transcript.read_text(encoding="utf-8")
    assert "Curious Explainer" in transcript
    assert "Skeptic" in transcript
    assert "Synthesizer" in transcript

    manifest = json.loads(result.artifacts.manifest.read_text(encoding="utf-8"))
    assert [source["origin"] for source in manifest["sources"]] == ["user", "supplemental"]

    metadata = json.loads(result.artifacts.metadata.read_text(encoding="utf-8"))
    assert metadata["network_required"] is False
    assert metadata["provider_mode"] == "fake"
    assert metadata["turn_count"] == 3

    with wave.open(str(result.artifacts.wav), "rb") as output:
        assert output.getframerate() == 24_000
        assert output.getnchannels() == 1
        assert output.getnframes() == 720

    database = Database(tmp_path / "projects" / result.project_id / "project.db")
    with database.connection() as db:
        origins = [
            row["origin"]
            for row in db.execute("SELECT origin FROM sources ORDER BY origin DESC").fetchall()
        ]
        turns = db.execute("SELECT COUNT(*) FROM conversation_turns").fetchone()[0]
        tts_artifacts = db.execute("SELECT COUNT(*) FROM tts_artifacts").fetchone()[0]
        timelines = db.execute("SELECT COUNT(*) FROM audio_timelines").fetchone()[0]
    assert origins == ["user", "supplemental"]
    assert turns == 3
    assert tts_artifacts == 3
    assert timelines == 1


def test_deterministic_fixture_rerun_uses_durable_stage_checkpoints(tmp_path):
    runner = deterministic_fixture.DeterministicFixtureRunner(WorkspaceManager(tmp_path))
    first = runner.run()
    second = runner.run()

    assert first.executed_stages == deterministic_fixture.DEFAULT_STAGES
    assert second.executed_stages == ()
    assert second.skipped_stages == deterministic_fixture.DEFAULT_STAGES
