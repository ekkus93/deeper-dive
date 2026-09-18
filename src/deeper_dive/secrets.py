"""Credential storage and centralized secret redaction."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

REDACTED = "[REDACTED]"


class CredentialStore(Protocol):
    """Minimal secret-store contract; callers persist only credential references."""

    def get(self, reference: str) -> str | None: ...

    def set(self, reference: str, secret: str) -> None: ...

    def delete(self, reference: str) -> None: ...


@dataclass(slots=True)
class EnvironmentCredentialStore:
    """Read credentials from explicit environment-variable references."""

    environ: Mapping[str, str] | None = None

    def get(self, reference: str) -> str | None:
        if not reference.startswith("env:"):
            return None
        name = reference.removeprefix("env:")
        if not name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError("invalid environment credential reference")
        return (self.environ or os.environ).get(name)

    def set(self, reference: str, secret: str) -> None:
        raise NotImplementedError("environment credentials are read-only")

    def delete(self, reference: str) -> None:
        raise NotImplementedError("environment credentials are read-only")


class KeyringCredentialStore:
    """OS keyring backend loaded lazily so headless installs remain usable."""

    def __init__(self, service_name: str = "deeper-dive") -> None:
        self.service_name = service_name

    @staticmethod
    def _keyring():
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError("OS keyring support requires the optional 'keyring' package") from exc
        return keyring

    def get(self, reference: str) -> str | None:
        return self._keyring().get_password(self.service_name, reference)

    def set(self, reference: str, secret: str) -> None:
        self._keyring().set_password(self.service_name, reference, secret)

    def delete(self, reference: str) -> None:
        keyring = self._keyring()
        try:
            keyring.delete_password(self.service_name, reference)
        except keyring.errors.PasswordDeleteError:
            return


@dataclass(slots=True)
class CredentialResolver:
    """Resolve keyring references with an explicit environment fallback."""

    primary: CredentialStore
    environment: EnvironmentCredentialStore

    def get(self, reference: str, *, environment_fallback: str | None = None) -> str | None:
        if reference.startswith("env:"):
            return self.environment.get(reference)
        value = self.primary.get(reference)
        if value is not None or environment_fallback is None:
            return value
        return self.environment.get(f"env:{environment_fallback}")


def redact_text(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    """Redact known values and common credential-bearing diagnostic syntax."""

    result = text
    for secret in sorted((value for value in secrets if value), key=len, reverse=True):
        result = result.replace(secret, REDACTED)
    patterns = (
        r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s,;]+",
        r"(?i)((?:api[_-]?key|token|secret|password)\s*[:=]\s*)[^\s,;]+",
    )
    for pattern in patterns:
        result = re.sub(pattern, rf"\1{REDACTED}", result)
    return result


def redact_data(value: object, secrets: list[str] | tuple[str, ...] = ()) -> object:
    """Recursively sanitize diagnostic/config structures without mutating inputs."""

    sensitive = {"authorization", "api_key", "apikey", "token", "secret", "password"}
    if isinstance(value, dict):
        return {
            key: REDACTED if str(key).lower() in sensitive else redact_data(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_data(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_data(item, secrets) for item in value)
    if isinstance(value, str):
        return redact_text(value, secrets)
    return value
