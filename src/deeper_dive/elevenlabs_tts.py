"""ElevenLabs adapter for the normalized TTS provider contract."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from deeper_dive.llm import ProviderHealth
from deeper_dive.tts import TTSAudioResult, TTSRequest, TTSVoice


class ElevenLabsTTSError(RuntimeError):
    """Normalized ElevenLabs provider failure."""


class ElevenLabsAuthError(ElevenLabsTTSError):
    pass


class ElevenLabsRateLimitError(ElevenLabsTTSError):
    pass


class ElevenLabsTimeoutError(ElevenLabsTTSError):
    pass


JsonRequest = Callable[[str, dict[str, str], float], dict[str, Any]]
BinaryRequest = Callable[[str, dict[str, object], dict[str, str], float], bytes]


def _map_http_error(exc: HTTPError) -> ElevenLabsTTSError:
    if exc.code in {401, 403}:
        return ElevenLabsAuthError("ElevenLabs authentication failed")
    if exc.code == 429:
        return ElevenLabsRateLimitError("ElevenLabs rate limit exceeded")
    return ElevenLabsTTSError(f"ElevenLabs HTTP error {exc.code}")


def _json_request(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured API URL
            value = json.loads(bytes(response.read()).decode("utf-8"))
    except TimeoutError as exc:
        raise ElevenLabsTimeoutError("ElevenLabs request timed out") from exc
    except HTTPError as exc:
        raise _map_http_error(exc) from exc
    except URLError as exc:
        raise ElevenLabsTTSError(f"ElevenLabs connection failed: {exc.reason}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ElevenLabsTTSError("ElevenLabs returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise ElevenLabsTTSError("ElevenLabs returned a non-object response")
    return value


def _binary_request(
    url: str, payload: dict[str, object], headers: dict[str, str], timeout: float
) -> bytes:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - configured API URL
            return bytes(response.read())
    except TimeoutError as exc:
        raise ElevenLabsTimeoutError("ElevenLabs synthesis timed out") from exc
    except HTTPError as exc:
        raise _map_http_error(exc) from exc
    except URLError as exc:
        raise ElevenLabsTTSError(f"ElevenLabs connection failed: {exc.reason}") from exc


class ElevenLabsTTSProvider:
    """ElevenLabs voice discovery and text-to-speech adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "eleven_multilingual_v2",
        base_url: str = "https://api.elevenlabs.io/v1",
        output_format: str = "mp3_44100_128",
        timeout: float = 60.0,
        request_json: JsonRequest = _json_request,
        request_binary: BinaryRequest = _binary_request,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._output_format = output_format
        self._timeout = timeout
        self._request_json = request_json
        self._request_binary = request_binary

    @property
    def provider_id(self) -> str:
        return "elevenlabs"

    def health(self) -> ProviderHealth:
        try:
            self.voices()
        except ElevenLabsTTSError as exc:
            return ProviderHealth(False, str(exc))
        return ProviderHealth(True, "ready")

    def voices(self) -> tuple[TTSVoice, ...]:
        value = self._request_json(f"{self._base_url}/voices", self._headers(), self._timeout)
        items = value.get("voices")
        if not isinstance(items, list):
            raise ElevenLabsTTSError("ElevenLabs voice response is missing voices")
        voices: list[TTSVoice] = []
        for item in items:
            if not isinstance(item, Mapping):
                continue
            voice_id = item.get("voice_id")
            name = item.get("name")
            if not isinstance(voice_id, str) or not isinstance(name, str):
                continue
            metadata: dict[str, str] = {}
            category = item.get("category")
            if isinstance(category, str):
                metadata["category"] = category
            voices.append(TTSVoice(voice_id, name, metadata=metadata))
        return tuple(voices)

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        if not request.text.strip():
            raise ValueError("speech text must not be empty")
        if not request.voice:
            raise ValueError("voice must not be empty")
        model = request.model or self._model
        payload: dict[str, object] = {"text": request.text, "model_id": model}
        voice_id = quote(request.voice, safe="")
        url = f"{self._base_url}/text-to-speech/{voice_id}?output_format={self._output_format}"
        audio = self._request_binary(url, payload, self._headers(), self._timeout)
        if not audio:
            raise ElevenLabsTTSError("ElevenLabs returned empty audio")
        audio_format, media_type = self._format_metadata()
        return TTSAudioResult(
            audio=audio,
            media_type=media_type,
            format=audio_format,
            provider=self.provider_id,
            voice=request.voice,
            model=model,
            sample_rate_hz=request.sample_rate_hz,
        )

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key}

    def _format_metadata(self) -> tuple[str, str]:
        if self._output_format.startswith("mp3"):
            return "mp3", "audio/mpeg"
        if self._output_format.startswith("pcm"):
            return "pcm", "audio/pcm"
        if self._output_format.startswith("ulaw"):
            return "ulaw", "audio/basic"
        return self._output_format, "application/octet-stream"
