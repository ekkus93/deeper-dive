from __future__ import annotations

import json
from pathlib import Path

from deeper_dive.llm import FakeLLMProvider, LLMMessage, LLMRequest
from deeper_dive.pipeline import DEFAULT_STAGES, PipelineContext, PipelineOrchestrator
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import EpisodeRecord, HostEpisodeRepository
from deeper_dive.storage.run_repositories import GenerationRunRecord, GenerationRunRepository
from deeper_dive.tts import FakeTTSProvider, TTSRequest, TTSVoice


def test_dd200_deterministic_fake_provider_pipeline(tmp_path: Path) -> None:
    """Qualify the V1 fixture without network, credentials, models, or FFmpeg."""
    fixture = Path(__file__).parent / "fixtures" / "dd200_primary.md"
    primary_text = fixture.read_text(encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()

    database = Database(tmp_path / "project.db")
    database.initialize()
    with database.transaction() as db:
        db.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES(?,?,?,?)",
            ("project-dd200", "DD-200 fixture", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    episodes = HostEpisodeRepository(database)
    episodes.create_episode(
        EpisodeRecord(
            id="episode-dd200",
            project_id="project-dd200",
            title="Deterministic fixture",
            created_at="2026-01-01T00:00:00Z",
            modified_at="2026-01-01T00:00:00Z",
        ),
        [],
    )
    runs = GenerationRunRepository(database)
    run = GenerationRunRecord(
        id="run-dd200",
        episode_id="episode-dd200",
        stage="sources",
        state="pending",
        created_at="2026-01-01T00:00:00Z",
        modified_at="2026-01-01T00:00:00Z",
    )
    runs.create(run)

    llm = FakeLLMProvider(response="A deterministic evidence-grounded turn.")
    tts = FakeTTSProvider(
        voices=(
            TTSVoice("explainer", "Explainer"),
            TTSVoice("skeptic", "Skeptic"),
            TTSVoice("historian", "Historian"),
        )
    )
    state: dict[str, object] = {}

    def sources(_: PipelineContext) -> None:
        state["sources"] = [{"id": "primary-1", "kind": "primary", "text": primary_text}]

    def research(_: PipelineContext) -> None:
        state["supplemental"] = [
            {
                "id": "supplemental-1",
                "kind": "supplemental",
                "gap": "corroborate synthetic sunrise",
                "text": "Fixture evidence confirms the synthetic 06:00 sunrise.",
            }
        ]

    def planning(_: PipelineContext) -> None:
        state["plan"] = {"hosts": ["explainer", "skeptic", "historian"]}

    def conversation(_: PipelineContext) -> None:
        turns = []
        for host in ("explainer", "skeptic", "historian"):
            response = llm.generate(
                LLMRequest((LLMMessage("user", f"{host}: discuss the fixture evidence"),))
            )
            turns.append({"host": host, "text": response.text})
        state["turns"] = turns

    def verification(_: PipelineContext) -> None:
        state["claims"] = [
            {"turn": index, "evidence": "primary-1", "verified": True} for index in range(3)
        ]

    def synthesize(_: PipelineContext) -> None:
        clips = []
        for turn in state["turns"]:  # type: ignore[union-attr]
            audio = tts.synthesize(TTSRequest(turn["text"], turn["host"]))
            clips.append(audio.audio)
        state["clips"] = clips

    def composition(_: PipelineContext) -> None:
        clips = state["clips"]
        assert isinstance(clips, list)
        (output / "episode.wav").write_bytes(b"".join(clips))

    def export(_: PipelineContext) -> None:
        turns = state["turns"]
        sources_value = state["sources"]
        supplemental = state["supplemental"]
        (output / "transcript.md").write_text(
            "\n".join(f"**{turn['host']}**: {turn['text']}" for turn in turns),
            encoding="utf-8",
        )
        (output / "source-manifest.json").write_text(
            json.dumps([*sources_value, *supplemental], sort_keys=True), encoding="utf-8"
        )
        (output / "metadata.json").write_text(
            json.dumps({"episode_id": "episode-dd200", "host_count": 3}, sort_keys=True),
            encoding="utf-8",
        )

    handlers = dict(
        zip(
            DEFAULT_STAGES,
            (
                sources,
                research,
                planning,
                conversation,
                verification,
                synthesize,
                composition,
                export,
            ),
            strict=True,
        )
    )
    result = PipelineOrchestrator(runs, handlers, max_stage_retries=0).run(run.id)

    assert result.run.state == "completed"
    assert result.executed_stages == DEFAULT_STAGES
    assert len(llm.requests) == 3
    assert len(tts.requests) == 3
    assert (output / "episode.wav").read_bytes().startswith(b"FAKE-WAV")
    assert "explainer" in (output / "transcript.md").read_text(encoding="utf-8")
    manifest = json.loads((output / "source-manifest.json").read_text(encoding="utf-8"))
    assert [item["kind"] for item in manifest] == ["primary", "supplemental"]
    assert json.loads((output / "metadata.json").read_text(encoding="utf-8"))["host_count"] == 3

    rerun = PipelineOrchestrator(runs, handlers, max_stage_retries=0).run(run.id)
    assert rerun.executed_stages == ()
    assert rerun.skipped_stages == DEFAULT_STAGES
    assert len(llm.requests) == 3
    assert len(tts.requests) == 3
