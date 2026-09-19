from pathlib import Path

import pytest

from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry, ProviderHealth
from deeper_dive.model_roles import ModelAssignment, ModelRole, ModelRoleAssignments
from deeper_dive.preflight import CloudPrice, PreflightBlockedError, PreflightService
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry


def assignments() -> ModelRoleAssignments:
    return ModelRoleAssignments(
        user={role: ModelAssignment("fake", "fake-v1") for role in ModelRole}
    )


def host() -> HostProfile:
    return HostProfile(
        id="host-1",
        project_id="project-1",
        display_name="Host",
        tts_provider="fake-tts",
        tts_voice="voice-a",
    )


def service() -> PreflightService:
    llm = LLMProviderRegistry()
    llm.register(FakeLLMProvider())
    tts = TTSProviderRegistry()
    tts.register(FakeTTSProvider())
    return PreflightService(llm, tts)


def test_preflight_ready_with_explicit_price(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    report = service().check(
        assignments=assignments(),
        hosts=(host(),),
        source_count=2,
        indexed_source_count=2,
        target_minutes=20,
        ffmpeg_executable=ffmpeg,
        cloud_prices=(CloudPrice("fake", "fake-v1", 10.0),),
    )
    assert report.ready
    assert report.estimate.estimated_words == 3000
    assert report.estimate.estimated_cloud_cost_usd is not None
    assert report.estimate.cloud_cost_is_estimate
    report.require_ready()


def test_preflight_blocks_missing_roles_sources_tts_and_ffmpeg(tmp_path: Path) -> None:
    report = service().check(
        assignments=ModelRoleAssignments(),
        hosts=(HostProfile(id="h", project_id="p", display_name="H"),),
        source_count=0,
        indexed_source_count=0,
        target_minutes=20,
        ffmpeg_executable=tmp_path / "missing-ffmpeg",
    )
    codes = {issue.code for issue in report.blockers}
    assert {"llm_assignment", "tts_assignment", "sources_missing", "ffmpeg_unavailable"} <= codes
    with pytest.raises(PreflightBlockedError, match="generation blocked"):
        report.require_ready()


def test_preflight_blocks_unindexed_sources(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    report = service().check(
        assignments=assignments(),
        hosts=(host(),),
        source_count=3,
        indexed_source_count=2,
        target_minutes=10,
        ffmpeg_executable=ffmpeg,
    )
    assert any(issue.code == "sources_unindexed" for issue in report.blockers)


def test_cloud_cost_absent_without_explicit_pricing(tmp_path: Path) -> None:
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    report = service().check(
        assignments=assignments(),
        hosts=(host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=ffmpeg,
    )
    assert report.estimate.estimated_cloud_cost_usd is None


class UnhealthyLLM(FakeLLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "offline")


def test_unhealthy_required_llm_is_hard_blocker(tmp_path: Path) -> None:
    llm = LLMProviderRegistry()
    llm.register(UnhealthyLLM())
    tts = TTSProviderRegistry()
    tts.register(FakeTTSProvider())
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("fake")
    report = PreflightService(llm, tts).check(
        assignments=assignments(),
        hosts=(host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=ffmpeg,
    )
    assert any(issue.code == "llm_unhealthy" for issue in report.blockers)
