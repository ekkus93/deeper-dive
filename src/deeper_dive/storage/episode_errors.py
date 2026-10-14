"""Typed episode configuration failures shared by storage and application layers."""

from __future__ import annotations


class EpisodeConfigurationError(ValueError):
    """Base class; subclasses ``ValueError`` so existing handlers keep working."""


class EpisodeFrozenError(EpisodeConfigurationError):
    """The episode has generation history and its configuration is immutable."""


class EpisodeConfigurationConflict(EpisodeConfigurationError):
    """The episode changed concurrently or is no longer editable; reload and retry."""
