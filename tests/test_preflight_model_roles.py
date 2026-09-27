from __future__ import annotations

from pathlib import Path

from deeper_dive.hosts import HostProfile
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry, ProviderHealth
from deeper_dive.model_roles import ModelAssignment, ModelRole, ModelRoleAssignments
from deeper_dive.preflight import PreflightReport, PreflightService
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


def _check_role(
    tmp_path: Path,
    role: ModelRole,
    assignment: ModelAssignment,
    provider: FakeLLMProvider | None = None,
) -> PreflightReport:
    assignments = ModelRoleAssignments(user={role: assignment})
    return _service(provider).check(
        assignments=assignments,
        hosts=(_host(),),
        source_count=1,
        indexed_source_count=1,
        target_minutes=10,
        ffmpeg_executable=_ffmpeg(tmp_path),
        required_model_roles=(role,),
    )


def _blocker_messages(report: PreflightReport) -> tuple[str, ...]:
    return tuple(issue.message for issue in report.blockers)


def test_unknown_directing_provider_blocks(tmp_path: Path) -> None:
    report = _check_role(
        tmp_path,
        ModelRole.DIRECTING,
        ModelAssignment("missing", "fake-v1"),
    )

    expected = "unknown provider 'missing' for directing"
    assert any(expected in message for message in _blocker_messages(report))


def test_unknown_verification_provider_blocks(tmp_path: Path) -> None:
    report = _check_role(
        tmp_path,
        ModelRole.VERIFICATION,
        ModelAssignment("missing", "fake-v1"),
    )

    expected = "unknown provider 'missing' for verification"
    assert any(expected in message for message in _blocker_messages(report))


def test_unavailable_directing_model_blocks(tmp_path: Path) -> None:
    report = _check_role(
        tmp_path,
        ModelRole.DIRECTING,
        ModelAssignment("fake", "missing-model"),
    )

    expected = "model 'missing-model' is unavailable from provider 'fake'"
    assert any(expected in message for message in _blocker_messages(report))


def test_unavailable_verification_model_blocks(tmp_path: Path) -> None:
    report = _check_role(
        tmp_path,
        ModelRole.VERIFICATION,
        ModelAssignment("fake", "missing-model"),
    )

    expected = "model 'missing-model' is unavailable from provider 'fake'"
    assert any(expected in message for message in _blocker_messages(report))


def test_unhealthy_directing_provider_blocks(tmp_path: Path) -> None:
    provider = UnhealthyLLM(provider_id="director")
    report = _check_role(
        tmp_path,
        ModelRole.DIRECTING,
        ModelAssignment("director", "fake-v1"),
        provider,
    )

    expected = "LLM provider 'director' is unhealthy"
    assert any(expected in message for message in _blocker_messages(report))


def test_unhealthy_verification_provider_blocks(tmp_path: Path) -> None:
    provider = UnhealthyLLM(provider_id="verifier")
    report = _check_role(
        tmp_path,
        ModelRole.VERIFICATION,
        ModelAssignment("verifier", "fake-v1"),
        provider,
    )

    expected = "LLM provider 'verifier' is unhealthy"
    assert any(expected in message for message in _blocker_messages(report))
