"""Versioned non-secret user configuration stored outside project workspaces."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CURRENT_CONFIG_VERSION = 1


class ProviderConfig(BaseModel):
    """Non-secret provider settings. Credentials are intentionally not represented."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    provider_type: str = Field(min_length=1)
    base_url: str | None = None
    default_model: str | None = None
    credential_env: str | None = None
    voices: tuple[str, ...] = ()
    response_format: str = "wav"
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    network_scope: Literal["local", "remote"] | None = None

    @field_validator("credential_env")
    @classmethod
    def validate_credential_env(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", cleaned):
            raise ValueError("credential_env must be an environment-variable name")
        return cleaned

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        try:
            parsed = urlsplit(value)
            host = parsed.hostname
            _ = parsed.port
        except ValueError:
            # URL parsing errors may contain user-controlled credential material.
            raise ValueError("base_url must contain a valid HTTP(S) host and port") from None
        if not host or any(ch.isspace() for ch in value):
            raise ValueError("base_url must include a valid HTTP(S) host")
        if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
            raise ValueError("base_url must not contain credentials in URL userinfo")
        sensitive = {
            "api_key",
            "apikey",
            "key",
            "token",
            "access_token",
            "auth",
            "authorization",
            "password",
            "secret",
        }
        if any(
            key.lower() in sensitive for key, _ in parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise ValueError("base_url must not contain credential query parameters")
        return value.rstrip("/")


class UserConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    schema_version: int = CURRENT_CONFIG_VERSION
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)

    @field_validator("schema_version")
    @classmethod
    def validate_version(cls, value: int) -> int:
        if value != CURRENT_CONFIG_VERSION:
            raise ValueError(
                f"unsupported user config schema_version {value}; expected {CURRENT_CONFIG_VERSION}"
            )
        return value


class UserConfigError(ValueError):
    """Actionable configuration load/validation failure."""


class UserConfigStore:
    """JSON-backed user config explicitly separate from per-project databases."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> UserConfig:
        if not self.path.exists():
            return UserConfig()
        try:
            raw = self.path.read_text(encoding="utf-8")
            return UserConfig.model_validate_json(raw)
        except ValidationError as exc:
            # Pydantic normally includes input_value, which may contain a raw secret.
            # Only return error locations and types, never the submitted values.
            location = ", ".join(
                ".".join(map(str, err["loc"])) or "configuration"
                for err in exc.errors(include_input=False, include_url=False)
            )
            raise UserConfigError(
                f"invalid user configuration at {self.path}: check {location}"
            ) from None
        except (OSError, ValueError):
            raise UserConfigError(f"invalid user configuration at {self.path}") from None

    def save(self, config: UserConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(config.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        self._restrict_permissions(temporary)
        temporary.replace(self.path)
        self._restrict_permissions(self.path)

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        if os.name == "posix":
            path.chmod(0o600)
