"""First-run readiness and local-only setup guidance."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass

from deeper_dive.provider_tui import ProviderController


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
        lines = [
            "Welcome to Deeper Dive. You can configure cloud providers or stay entirely local.",
            f"FFmpeg: {'available' if self.ffmpeg_available else 'not found — install FFmpeg before audio assembly.'}",
            f"KittenTTS Micro: {'runtime available' if self.kitten_available else 'optional runtime not installed — install the KittenTTS optional dependency to enable local CPU speech.'}",
        ]
        if self.configured_providers:
            lines.append("Configured providers: " + ", ".join(self.configured_providers))
        else:
            lines.append("Providers: none configured. This is valid; cloud configuration may be skipped.")
        if self.local_providers:
            lines.append("Local providers: " + ", ".join(self.local_providers))
        else:
            lines.append("Local LLM option: add an Ollama or llama-server/OpenAI-compatible endpoint when ready.")
        lines.append("Start by creating an empty project and adding your own sources; no copyrighted sample content is bundled.")
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
                if provider.provider_type.lower() in {"ollama", "llama-server", "llama_server", "local"}
                or (provider.base_url or "").startswith(("http://127.0.0.1", "http://localhost"))
            )
        )
        return FirstRunStatus(
            ffmpeg_available=shutil.which("ffmpeg") is not None,
            kitten_available=importlib.util.find_spec("kittentts") is not None,
            configured_providers=names,
            local_providers=local,
        )
