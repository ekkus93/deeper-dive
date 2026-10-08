"""First-run readiness, explicit system checks, and local-only setup guidance."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from deeper_dive.diagnostics import sanitize_exception_message
from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig

LOCAL_PROVIDER_TYPES = {"ollama", "llama-server", "llama_server", "local"}
LOCAL_URL_PREFIXES = ("http://127.0.0.1", "http://localhost")
_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_DEFAULT_LLAMA_SERVER_URL = "http://127.0.0.1:8080"


def _is_local(provider: ProviderConfig) -> bool:
    kind = provider.provider_type.lower()
    url = provider.base_url or ""
    return kind in LOCAL_PROVIDER_TYPES or url.startswith(LOCAL_URL_PREFIXES)


@dataclass(frozen=True, slots=True)
class FirstRunStatus:
    ffmpeg_available: bool
    kitten_available: bool
    configured_providers: tuple[str, ...]
    local_providers: tuple[str, ...]

    @property
    def cloud_required(self) -> bool:
        return False

    @property
    def can_continue_local_only(self) -> bool:
        return self.kitten_available or bool(self.local_providers)

    def guidance(self) -> tuple[str, ...]:
        lines = ["Welcome to Deeper Dive. Cloud providers are optional."]
        lines.append(self._ffmpeg_guidance())
        lines.append(self._kitten_guidance())
        lines.append(self._provider_guidance())
        lines.append(self._local_guidance())
        lines.append("Create an empty project and add your own sources.")
        lines.append("No copyrighted sample content is bundled.")
        return tuple(lines)

    def _ffmpeg_guidance(self) -> str:
        if self.ffmpeg_available:
            return "FFmpeg: available"
        return "FFmpeg: not found. Install FFmpeg before audio assembly."

    def _kitten_guidance(self) -> str:
        if self.kitten_available:
            return "KittenTTS Micro: runtime available"
        return "KittenTTS optional dependency is not installed; install it for local CPU speech."

    def _provider_guidance(self) -> str:
        if not self.configured_providers:
            return "Providers: none configured; cloud configuration may be skipped."
        names = ", ".join(self.configured_providers)
        return f"Configured providers: {names}"

    def _local_guidance(self) -> str:
        if not self.local_providers:
            return "Local LLM option: add an Ollama or llama-server endpoint."
        names = ", ".join(self.local_providers)
        return f"Local providers: {names}"


@dataclass(frozen=True, slots=True)
class FirstRunSystemCheck:
    """One bounded observation of local first-run dependencies."""

    python_runtime: str
    ffmpeg_available: bool
    kitten_available: bool
    ollama_reachable: bool
    llama_server_reachable: bool
    diagnostics: tuple[str, ...]

    def summary(self) -> tuple[str, ...]:
        kitten = (
            "Ready"
            if self.kitten_available
            else "Optional / not installed (needed only when KittenTTS is selected)"
        )
        return (
            f"Python/runtime: Ready ({self.python_runtime})",
            f"FFmpeg: {'Ready' if self.ffmpeg_available else 'Needs attention for audio'}",
            f"KittenTTS: {kitten}",
            f"Ollama: {'Detected' if self.ollama_reachable else 'Not detected (optional)'}",
            (
                "llama-server: Detected"
                if self.llama_server_reachable
                else "llama-server: Not detected (optional)"
            ),
        )


EndpointProbe = Callable[[str], bool]


class FirstRunController:
    """Readiness and explicit system checks for first-run UI and smoke tests."""

    def __init__(self, providers: ProviderController) -> None:
        self.providers = providers

    def status(self) -> FirstRunStatus:
        """Return the historical side-effect-free readiness probe."""

        config = self.providers.config()
        names = tuple(sorted(config.providers))
        local_names = []
        for name, provider in config.providers.items():
            if _is_local(provider):
                local_names.append(name)
        local = tuple(sorted(local_names))
        return FirstRunStatus(
            ffmpeg_available=shutil.which("ffmpeg") is not None,
            kitten_available=importlib.util.find_spec("kittentts") is not None,
            configured_providers=names,
            local_providers=local,
        )

    def system_check(self, endpoint_probe: EndpointProbe | None = None) -> FirstRunSystemCheck:
        """Explicitly probe optional local endpoints for the setup wizard."""

        status = self.status()
        probe = endpoint_probe or _probe_endpoint
        diagnostics: list[str] = []
        ollama_url = self._configured_base_url("ollama") or _DEFAULT_OLLAMA_URL
        llama_url = self._configured_base_url("llama-server") or _DEFAULT_LLAMA_SERVER_URL
        ollama = self._safe_probe(
            "Ollama",
            f"{ollama_url.rstrip('/')}/api/tags",
            probe,
            diagnostics,
        )
        llama = self._safe_probe(
            "llama-server",
            f"{llama_url.rstrip('/')}/health",
            probe,
            diagnostics,
        )
        return FirstRunSystemCheck(
            python_runtime=f"Python {sys.version_info.major}.{sys.version_info.minor}",
            ffmpeg_available=status.ffmpeg_available,
            kitten_available=status.kitten_available,
            ollama_reachable=ollama,
            llama_server_reachable=llama,
            diagnostics=tuple(diagnostics),
        )

    def _configured_base_url(self, provider_type: str) -> str | None:
        target = provider_type.strip().lower().replace("_", "-")
        for provider in self.providers.config().providers.values():
            kind = provider.provider_type.strip().lower().replace("_", "-")
            if kind == target and provider.base_url:
                return provider.base_url
        return None

    @staticmethod
    def _safe_probe(
        label: str,
        url: str,
        probe: EndpointProbe,
        diagnostics: list[str],
    ) -> bool:
        try:
            reachable = bool(probe(url))
        except Exception as exc:
            diagnostics.append(f"{label}: {sanitize_exception_message(exc)}")
            return False
        diagnostics.append(f"{label}: {'reachable' if reachable else 'not reachable'}")
        return reachable


def _probe_endpoint(url: str) -> bool:
    """Use a short reachability probe; no setup state is mutated."""

    request = Request(url, headers={"User-Agent": "deeper-dive-first-run"})
    try:
        with urlopen(request, timeout=0.35) as response:
            return 200 <= int(response.status) < 500
    except HTTPError:
        return True
    except (URLError, OSError, ValueError):
        return False
