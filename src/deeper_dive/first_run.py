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
    provider_type = provider.provider_type.lower()
    base_url = provider.base_url or ""
    return provider_type in LOCAL_PROVIDER_TYPES or base_url.startswith(LOCAL_URL_PREFIXES)


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
        if self.ffmpeg_available:
            lines.append("FFmpeg: available")
        else:
            lines.append("FFmpeg: not found. Install FFmpeg before audio assembly.")
        if self.kitten_available:
            lines.append("KittenTTS Micro: runtime available")
        else:
            lines.append(
                "KittenTTS Micro: optional runtime not installed. "
                "Install the KittenTTS optional dependency for local CPU speech."
            )
        if self.configured_providers:
            names = ", ".join(self.configured_providers)
            lines.append(f"Configured providers: {names}")
        else:
            lines.append("Providers: none configured. Cloud configuration may be skipped.")
        if self.local_providers:
            names = ", ".join(self.local_providers)
            lines.append(f"Local providers: {names}")
        else:
            lines.append(
                "Local LLM option: add an Ollama or llama-server endpoint when ready."
            )
        lines.append(
            "Create an empty project and add your own sources; "
            "no copyrighted sample content is bundled."
        )
        return tuple(lines)


class FirstRunController:
    """Side-effect-free readiness probe used by first-run UI and smoke tests."""

    def __init__(self, providers: ProviderController) -> None:
        self.providers = providers

    def status(self) -> FirstRunStatus:
        config = self.providers.config()
        names = tuple(sorted(config.providers))
        local = tuple(
            sorted(
                name
                for name, provider in config.providers.items()
                if _is_local(provider)
            )
        )
        return FirstRunStatus(
            ffmpeg_available=shutil.which("ffmpeg") is not None,
            kitten_available=importlib.util.find_spec("kittentts") is not None,
            configured_providers=names,
            local_providers=local,
        )
