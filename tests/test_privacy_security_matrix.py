from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from deeper_dive.audio_timeline import AudioTimeline, TimelineItem
from deeper_dive.diagnostics import DiagnosticEvent, StructuredDiagnosticLog, export_diagnostic_bundle
from deeper_dive.domain.errors import UserError
from deeper_dive.ffmpeg import FFmpegComposer, FFmpegConfig
from deeper_dive.llm import FakeLLMProvider, LLMProviderRegistry
from deeper_dive.research_fetch import ResearchFetchError, ResearchSafeFetcher
from deeper_dive.search import FetchRequest
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry


def test_secret_redaction_and_diagnostic_bundle_privacy_defaults(tmp_path: Path) -> None:
    secret = "matrix-secret-value"
    log_path = tmp_path / "diagnostics.jsonl"
    StructuredDiagnosticLog(log_path).emit(
        DiagnosticEvent(
            level="error",
            event="provider_request",
            provider="openai",
            details={"Authorization": f"Bearer {secret}", "api_key": secret},
        )
    )
    assert secret not in log_path.read_text()

    bundle = export_diagnostic_bundle(
        tmp_path / "bundle.json",
        configuration={"token": secret},
        source_excerpts={"source": "private corpus text"},
    )
    payload = bundle.read_text()
    assert secret not in payload
    assert "private corpus text" not in payload
    assert '"source_excerpts_included": false' in payload


def test_provider_routing_is_explicit_and_transparent() -> None:
    llm_registry = LLMProviderRegistry()
    llm_registry.register(FakeLLMProvider(provider_id="openai-route"))
    tts_registry = TTSProviderRegistry()
    tts_registry.register(FakeTTSProvider(provider_id="elevenlabs-route"))

    assert llm_registry.provider_ids() == ("openai-route",)
    assert llm_registry.get("openai-route").provider_id == "openai-route"
    assert tts_registry.provider_ids() == ("elevenlabs-route",)
    assert tts_registry.get("elevenlabs-route").provider_id == "elevenlabs-route"


def test_automated_research_rejects_private_network_targets() -> None:
    def private_resolver(host: str, port: int, *, type: int):
        import socket

        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    fetcher = ResearchSafeFetcher(resolver=private_resolver)
    with pytest.raises(ResearchFetchError, match="non-public"):
        fetcher.fetch(FetchRequest("http://localhost/private"))


def test_project_paths_reject_traversal(tmp_path: Path) -> None:
    manager = WorkspaceManager(tmp_path / "data")
    project = manager.create_project("00000000-0000-4000-8000-000000000001")
    with pytest.raises(UserError, match="escapes project workspace"):
        manager.resolve_project_path(project.project_id, "../../outside")


def test_ffmpeg_invocation_is_argv_only_and_never_uses_shell(tmp_path: Path) -> None:
    clip = tmp_path / "clip;touch-pwned.wav"
    clip.write_bytes(b"audio")
    timeline = AudioTimeline.build(
        "episode",
        (TimelineItem.clip(turn_id="turn", host_id="host", artifact_id="clip", duration_seconds=1),),
    )
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        FFmpegComposer(FFmpegConfig(Path("ffmpeg"))).compose(
            timeline, {"clip": clip}, tmp_path / "output.wav"
        )

    assert run.call_args.kwargs["shell"] is False
    assert str(clip) in run.call_args.args[0]
