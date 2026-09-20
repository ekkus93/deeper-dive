"""Actionable, secret-safe error messages for user-facing surfaces."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.diagnostics import redact


@dataclass(frozen=True, slots=True)
class UserError:
    summary: str
    action: str
    diagnostic: str

    @property
    def message(self) -> str:
        return f"{self.summary} {self.action}"


def actionable_error(area: str, exc: BaseException) -> UserError:
    """Convert common operational failures into actionable text plus safe diagnostics."""
    detail = str(redact(str(exc)))
    normalized = area.strip().lower()
    guidance = {
        "parser": (
            "Could not parse the source.",
            "Check that the file is supported and not damaged.",
        ),
        "provider": (
            "Provider request failed.",
            "Check provider health, credentials, model, and network settings.",
        ),
        "network": (
            "Network request failed.",
            "Check the URL, connectivity, redirects, and provider availability.",
        ),
        "tts": (
            "Speech generation failed.",
            "Check the TTS provider, selected voice, and model installation.",
        ),
        "ffmpeg": (
            "Audio processing failed.",
            "Check that FFmpeg is installed and available to Deeper Dive.",
        ),
    }
    summary, action = guidance.get(
        normalized,
        (
            "Operation failed.",
            "Review the diagnostics and retry after correcting the reported problem.",
        ),
    )
    return UserError(summary, action, detail)
