"""First-run readiness and local-only setup guidance."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from deeper_dive.provider_tui import ProviderController
from deeper_dive.user_config import ProviderConfig

LOCAL_PROVIDER_TYPES = {"ollama", "llama-server", "llama_server", "local"}
LOCAL_URL_PREFIXES = ("http://127.0.0.1", "http://localhost")


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
        return "KittenTTS Micro: install the optional runtime for local CPU speech."

    def _provider_guidance(self) -> str:
        if not self.configured_providers:
            return "Providers: none configured. Cloud configuration may be skipped."
        names = ", ".join(self.configured_providers)
        return f"Configured providers: {names}"

    def _local_guidance(self) -> str:
        if not self.local_providers:
            return "Local LLM option: add an Ollama or llama-server endpoint."
        names = ", ".join(self.local_providers)
        return f"Local providers: {names}"


class FirstRunController:
    """Side-effect-free readiness probe for first-run UI and smoke tests."""

    def __init__(self, providers: ProviderController) -> None:
        self.providers = providers

    def status(self) -> FirstRunStatus:
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
