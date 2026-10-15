"""Typed episode configuration failures shared by storage and application layers."""

from __future__ import annotations


class EpisodeConfigurationError(ValueError):
    """Base class; subclasses ``ValueError`` so existing handlers keep working."""


class EpisodeFrozenError(EpisodeConfigurationError):
    """The episode has generation history and its configuration is immutable."""


class EpisodeConfigurationConflict(EpisodeConfigurationError):
    """The episode changed concurrently or is no longer editable; reload and retry."""


class GenerationRunStillStopping(ValueError):
    """A cancel-requested run is still active; wait for it to stop before starting again."""


class InvalidModelOverrides(EpisodeConfigurationError):
    """Stored per-episode model overrides nothing can use; ``--clear-model-overrides`` fixes it."""

    REPAIR = (
        "repair it with `deeper-dive episode configure <project_id> <episode_id> "
        "--clear-model-overrides`"
    )

    def __init__(self, detail: str) -> None:
        super().__init__(f"{detail}; {self.REPAIR}")
        self.detail = detail

    def describe(self, project_id: str, episode_id: str) -> str:
        """The message with the repair command naming the real project and episode."""

        return str(self).replace("<project_id>", project_id).replace("<episode_id>", episode_id)
