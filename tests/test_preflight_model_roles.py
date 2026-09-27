from __future__ import annotations

from pathlib import Path

from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry, ProviderHealth
from deeper_dive.model_roles import ModelAssignment, ModelRole, ModelRoleAssignments
from deeper_dive.preflight import PreflightService
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry


class UnhealthyLLM(FakeLLMProvider):
    def health(self) -> ProviderHealth:
        return ProviderHealth(False, "offline")


def _host() -> HostProfile:
    return HostProfile(
        id="host-1",
        project_id="project-1",
        display_name="Host",
        tts_provider="fake-tts",
        tts_voice="voice-a",
    )


def _ffmpeg(tmp_path: Path) -> Path:
    path = tmp_path / "ffmpeg"
    path.write_text("fake")
    return path


def _service(provider: FakeLLMProvider | None = None) -> PreflightService:
    llm = LLMProviderRegistry()
    llm.register(provider or FakeLLMProvider())
    tts = TTSProviderRegistry()
    tts.register(FakeTTSProvider())
    return PreflightService(llm, tts)


def test_unknown_directing_provider_blocks(tmp_path: Path) -> None:
    report = _service().check(
        assignments=ModelRoleAssignments(
            user={
                ModelRole.DIRECTING: ModelAssignment("missing", "fake-v1"),
            }
        ),
        hosts=(_host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=_ffmpeg(tmp_path),
        required_model_roles=(ModelRole.DIRECTING,),
    )

    assert any(
        issue.code == "llm_assignment"
        and "unknown provider 'missing' for directing" in issue.message
        for issue in report.blockers
    )


def test_unavailable_verification_model_blocks(tmp_path: Path) -> None:
    report = _service().check(
        assignments=ModelRoleAssignments(
            user={
                ModelRole.VERIFICATION: ModelAssignment("fake", "missing-model"),
            }
        ),
        hosts=(_host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=_ffmpeg(tmp_path),
        required_model_roles=(ModelRole.VERIFICATION,),
    )

    assert any(
        issue.code == "llm_assignment"
        and "model 'missing-model' is unavailable from provider 'fake'" in issue.message
        for issue in report.blockers
    )


def test_unhealthy_directing_provider_blocks(tmp_path: Path) -> None:
    report = _service(UnhealthyLLM(provider_id="director")).check(
        assignments=ModelRoleAssignments(
            user={
                ModelRole.DIRECTING: ModelAssignment("director", "fake-v1"),
            }
        ),
        hosts=(_host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=_ffmpeg(tmp_path),
        required_model_roles=(ModelRole.DIRECTING,),
    )

    assert any(
        issue.code == "llm_unhealthy"
        and "LLM provider 'director' is unhealthy" in issue.message
        for issue in report.blockers
    )
