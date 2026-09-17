"""Structured application exception hierarchy."""


class AppError(Exception):
    """Base class for expected application-level failures."""


class UserError(AppError):
    """Invalid user input or an action that cannot be completed as requested."""


class ConfigurationError(AppError):
    """Missing or invalid application configuration."""


class ProviderError(AppError):
    """Failure while using a configured model or service provider."""


class StorageError(AppError):
    """Persistence or filesystem failure."""


class RecoverableError(AppError):
    """Transient failure for which retry or resume is expected to be safe."""
