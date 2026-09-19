from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import pytest

from deeper_dive.openai_compatible_tts import (
    OpenAICompatibleTTSError,
    OpenAICompatibleTTSProvider,
)
from deeper_dive.tts import TTSRequest


class _SpeechHandler(BaseHTTPRequestHandler):
    received: ClassVar[dict[str, object] | None] = None
    authorization: ClassVar[str | None] = None

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        type(self).received = json.loads(self.rfile.read(length))
        type(self).authorization = self.headers.get("X-API-Key")
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav; charset=binary")
        self.end_headers()
        self.wfile.write(b"RIFF-compatible-audio")

    def log_message(self, format: str, *args: object) -> None:
        pass


def test_compatible_tts_against_local_fake_http_server() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SpeechHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        provider = OpenAICompatibleTTSProvider(
            provider_id="local-speech",
            base_url=f"http://127.0.0.1:{server.server_port}",
            model="local-model",
            voices=("speaker-1", "speaker-2"),
            api_key="secret",
            credential_header="X-API-Key",
            credential_prefix="",
            timeout=2.0,
        )
        result = provider.synthesize(TTSRequest("Hello local", "speaker-2"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert result.audio == b"RIFF-compatible-audio"
    assert result.media_type == "audio/wav"
    assert result.provider == "local-speech"
    assert _SpeechHandler.received == {
        "model": "local-model",
        "input": "Hello local",
        "voice": "speaker-2",
        "response_format": "wav",
    }
    assert _SpeechHandler.authorization == "secret"


def test_compatible_tts_allows_model_format_headers_and_media_fallback() -> None:
    seen: dict[str, object] = {}

    def request(
        url: str, payload: dict[str, object], headers: dict[str, str], timeout: float
    ) -> tuple[bytes, str | None]:
        seen.update({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
        return b"mp3", None

    provider = OpenAICompatibleTTSProvider(
        provider_id="custom",
        base_url="http://localhost:9999/v1",
        model="default",
        voices=("v",),
        extra_headers={"X-Tenant": "demo"},
        response_format="mp3",
        request_binary=request,
    )
    result = provider.synthesize(TTSRequest("Hi", "v", model="override", response_format="mp3"))

    assert result.media_type == "audio/mpeg"
    assert result.model == "override"
    assert seen["headers"] == {"X-Tenant": "demo"}


def test_compatible_tts_rejects_invalid_config_and_provider_deviations() -> None:
    with pytest.raises(ValueError, match="HTTP"):
        OpenAICompatibleTTSProvider(
            provider_id="x", base_url="file:///tmp", model="m", voices=("v",)
        )

    provider = OpenAICompatibleTTSProvider(
        provider_id="x",
        base_url="http://localhost",
        model="m",
        voices=("v",),
        request_binary=lambda *args: (b"", "text/plain"),
    )
    with pytest.raises(OpenAICompatibleTTSError, match="empty audio"):
        provider.synthesize(TTSRequest("Hi", "v"))
    with pytest.raises(ValueError, match="voice"):
        provider.synthesize(TTSRequest("Hi", "missing"))
