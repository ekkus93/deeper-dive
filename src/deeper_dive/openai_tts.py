"""OpenAI Speech API adapter for the normalized TTS provider contract."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deeper_dive.llm import ProviderHealth
from deeper_dive.tts import TTSAudioResult, TTSRequest, TTSVoice


class OpenAITTSError(RuntimeError):
    """Normalized OpenAI speech-provider failure."""


class OpenAITTSAuthError(OpenAITTSError):
    pass


class OpenAITTSRateLimitError(OpenAITTSError):
    pass


class OpenAITTSTimeoutError(OpenAITTSError):
    pass


BinaryRequest = Callable[[str, dict[str, object], dict[str, str], float], bytes]
Sleep = Callable[[float], None]


_MEDIA_TYPES = {
    "aac": "audio/aac",
    "flac": "audio/flac",
    "mp3": "audio/mpeg",
    "opus": "audio/ogg",
    "pcm": "audio/pcm",
    "wav": "audio/wav",
}

# OpenAI does not currently expose a voice-list endpoint. Keep this capability
# explicit and deterministic until provider-side discovery is available.
_OPENAI_VOICES = (
    "alloy",
    "ash",
    "ballad",
    "coral",
    "echo",
    "fable",
    "nova",
    "onyx",
    "sage",
    "shimmer",
)


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
            return response.read()
    except TimeoutError as exc:
        raise OpenAITTSTimeoutError("OpenAI speech request timed out") from exc
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise OpenAITTSAuthError("OpenAI speech authentication failed") from exc
        if exc.code == 429:
            raise OpenAITTSRateLimitError("OpenAI speech rate limit exceeded") from exc
        raise OpenAITTSError(f"OpenAI speech HTTP error {exc.code}") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise OpenAITTSTimeoutError("OpenAI speech request timed out") from exc
        raise OpenAITTSError(f"OpenAI speech connection failed: {exc.reason}") from exc


class OpenAITTSProvider:
    """OpenAI ``/audio/speech`` adapter with bounded transient retries."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        max_retries: int = 2,
        request_binary: BinaryRequest = _binary_request,
        sleep: Sleep = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if not model:
            raise ValueError("model must not be empty")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._request = request_binary
        self._sleep = sleep

    @property
    def provider_id(self) -> str:
        return "openai"

    def health(self) -> ProviderHealth:
        # Avoid billable synthesis merely to probe health. Configuration is
        # validated here; an actual request reports normalized provider errors.
        return ProviderHealth(True, "configured")

    def voices(self) -> tuple[TTSVoice, ...]:
        return tuple(
            TTSVoice(voice, voice.title(), ("multilingual",), {"discovery": "static"})
            for voice in _OPENAI_VOICES
        )

    def synthesize(self, request: TTSRequest) -> TTSAudioResult:
        if not request.text.strip():
            raise ValueError("speech text must not be empty")
        if request.voice not in _OPENAI_VOICES:
            raise ValueError(f"unsupported OpenAI voice: {request.voice}")
        response_format = request.response_format.lower()
        if response_format not in _MEDIA_TYPES:
            raise ValueError(f"unsupported OpenAI speech format: {request.response_format}")
        model = request.model or self._model
        payload: dict[str, object] = {
            "model": model,
            "input": request.text,
            "voice": request.voice,
            "response_format": response_format,
        }
        audio = self._with_retry(payload)
        if not audio:
            raise OpenAITTSError("OpenAI speech returned empty audio")
        return TTSAudioResult(
            audio=audio,
            media_type=_MEDIA_TYPES[response_format],
            format=response_format,
            provider=self.provider_id,
            voice=request.voice,
            model=model,
            sample_rate_hz=request.sample_rate_hz,
        )

    def _with_retry(self, payload: dict[str, object]) -> bytes:
        attempts = 0
        while True:
            attempts += 1
            try:
                return self._request(
                    f"{self._base_url}/audio/speech",
                    payload,
                    {"Authorization": f"Bearer {self._api_key}"},
                    self._timeout,
                )
            except (OpenAITTSRateLimitError, OpenAITTSTimeoutError):
                if attempts > self._max_retries:
                    raise
                self._sleep(min(0.25 * (2 ** (attempts - 1)), 2.0))
