"""Generic OpenAI-compatible Speech API TTS adapter."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deeper_dive.llm import ProviderHealth
from deeper_dive.tts import TTSAudioResult, TTSRequest, TTSVoice


class OpenAICompatibleTTSError(RuntimeError):
    """Normalized failure from an OpenAI-compatible speech endpoint."""


BinaryRequest = Callable[[str, dict[str, object], dict[str, str], float], tuple[bytes, str | None]]


_MEDIA_TYPES = {
    "aac": "audio/aac",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "pcm": "audio/pcm",
    "wav": "audio/wav",
}


def _request_binary(
    url: str, payload: dict[str, object], headers: dict[str, str], timeout: float
) -> tuple[bytes, str | None]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - user-configured endpoint
            return bytes(response.read()), response.headers.get("Content-Type")
    except TimeoutError as exc:
        raise OpenAICompatibleTTSError("compatible TTS request timed out") from exc
    except HTTPError as exc:
        raise OpenAICompatibleTTSError(f"compatible TTS HTTP error {exc.code}") from exc
    except URLError as exc:
        raise OpenAICompatibleTTSError(f"compatible TTS connection failed: {exc.reason}") from exc


class OpenAICompatibleTTSProvider:
    """Configurable adapter for servers implementing ``/audio/speech``."""

    def __init__(
        self,
        *,
        provider_id: str,
        base_url: str,
        model: str,
        voices: tuple[str, ...],
        api_key: str | None = None,
        credential_header: str = "Authorization",
        credential_prefix: str = "Bearer ",
        extra_headers: Mapping[str, str] | None = None,
        response_format: str = "wav",
        timeout: float = 60.0,
        request_binary: BinaryRequest = _request_binary,
    ) -> None:
        if not provider_id:
            raise ValueError("provider_id must not be empty")
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use HTTP or HTTPS")
        if not model:
            raise ValueError("model must not be empty")
        if not voices or any(not voice for voice in voices):
            raise ValueError("at least one non-empty voice is required")
        if response_format.lower() not in _MEDIA_TYPES:
            raise ValueError(f"unsupported response format: {response_format}")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._provider_id = provider_id
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._voices = voices
        self._api_key = api_key
        self._credential_header = credential_header
        self._credential_prefix = credential_prefix
        self._extra_headers = dict(extra_headers or {})
        self._response_format = response_format.lower()
        self._timeout = timeout
        self._request = request_binary

    @property
    def provider_id(self) -> str:
        return self._provider_id

    def health(self) -> ProviderHealth:
        return ProviderHealth(True, "configured")

    def voices(self) -> tuple[TTSVoice, ...]:
        return tuple(TTSVoice(voice, voice) for voice in self._voices)

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        if not request.text.strip():
            raise ValueError("speech text must not be empty")
        if request.voice not in self._voices:
            raise ValueError(f"unknown compatible TTS voice: {request.voice}")
        response_format = (request.response_format or self._response_format).lower()
        if response_format not in _MEDIA_TYPES:
            raise ValueError(f"unsupported response format: {response_format}")
        model = request.model or self._model
        payload: dict[str, object] = {
            "model": model,
            "input": request.text,
            "voice": request.voice,
            "response_format": response_format,
        }
        audio, content_type = self._request(
            f"{self._base_url}/audio/speech", payload, self._headers(), self._timeout
        )
        if not audio:
            raise OpenAICompatibleTTSError("compatible TTS returned empty audio")
        media_type = self._normalized_media_type(content_type, response_format)
        return TTSAudioResult(
            audio=audio,
            media_type=media_type,
            format=response_format,
            provider=self.provider_id,
            voice=request.voice,
            model=model,
            sample_rate_hz=request.sample_rate_hz,
        )

    def _headers(self) -> dict[str, str]:
        headers = dict(self._extra_headers)
        if self._api_key:
            headers[self._credential_header] = f"{self._credential_prefix}{self._api_key}"
        return headers

    @staticmethod
    def _normalized_media_type(content_type: str | None, response_format: str) -> str:
        # Compatible servers commonly omit Content-Type or append parameters.
        if content_type:
            media_type = content_type.partition(";")[0].strip().lower()
            if media_type.startswith("audio/") or media_type == "application/octet-stream":
                return media_type
        return _MEDIA_TYPES[response_format]
