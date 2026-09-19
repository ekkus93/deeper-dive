from pathlib import Path

from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.model_roles import ModelAssignment, ModelRole, ModelRoleAssignments
from deeper_dive.preflight import PreflightService
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry


def _service() -> PreflightService:
    llm = LLMProviderRegistry()
    llm.register(FakeLLMProvider())
    tts = TTSProviderRegistry()
    tts.register(FakeTTSProvider())
    return PreflightService(llm, tts)


def _assignments() -> ModelRoleAssignments:
    return ModelRoleAssignments(user={role: ModelAssignment("fake", "fake-v1") for role in ModelRole})


def _host() -> HostProfile:
    return HostProfile(
        id="h",
        project_id="p",
        display_name="Host",
        tts_provider="fake-tts",
        tts_voice="voice-a",
    )


def test_preflight_discloses_remote_content_routes(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    report = _service().check(
        assignments=_assignments(),
        hosts=(_host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=ffmpeg,
        local_provider_ids=frozenset({"fake-tts"}),
    )
    assert report.ready
    assert any(route.provider == "fake" and not route.local for route in report.routes)
    assert any(route.provider == "fake-tts" and route.local for route in report.routes)
    assert any(issue.code == "source_content_remote" for issue in report.warnings)


def test_local_only_mode_blocks_remote_provider_routes(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    report = _service().check(
        assignments=_assignments(),
        hosts=(_host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=ffmpeg,
        local_provider_ids=frozenset({"fake-tts"}),
        local_only=True,
    )
    assert not report.ready
    assert any(issue.code == "local_only_violation" for issue in report.blockers)
    assert any(issue.code == "source_content_remote" for issue in report.blockers)
