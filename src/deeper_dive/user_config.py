"""Versioned non-secret user configuration stored outside project workspaces."""

from __future__ import annotations

import json
import os
import re
import tempfile
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock
from typing import IO, Iterator, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, ValidationError, field_validator

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None  # type: ignore[assignment]

CURRENT_CONFIG_VERSION = 1

_PATH_LOCKS_GUARD = Lock()
_PATH_LOCKS: dict[str, RLock] = {}

_RESEARCH_MODES = frozenset({"off", "conservative", "useful", "aggressive"})
_HOST_PRESETS = frozenset(
    {
        "curious_explainer",
        "skeptic",
        "synthesizer",
        "domain_expert",
        "practitioner",
        "historian",
        "moderator",
        "custom",
    }
)
_BOOLEAN_DEFAULTS = frozenset({"0", "1", "false", "true", "no", "yes", "off", "on"})


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
        if parsed.fragment:
            raise ValueError("base_url must not contain URL fragments")
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

    _revision: str | None = PrivateAttr(default=None)
    schema_version: int = CURRENT_CONFIG_VERSION
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)

    @field_validator("defaults")
    @classmethod
    def validate_defaults(cls, values: dict[str, str]) -> dict[str, str]:
        normalized = dict(values)
        for key in ("research_policy", "quick_deep_dive_research_policy"):
            raw = normalized.get(key)
            if raw is None:
                continue
            value = raw.strip().lower()
            if value and value not in _RESEARCH_MODES:
                raise ValueError(f"{key} must be one of: {', '.join(sorted(_RESEARCH_MODES))}")
            normalized[key] = value

        duration = normalized.get("quick_deep_dive_duration_minutes")
        if duration is not None:
            value = duration.strip()
            if value:
                try:
                    minutes = int(value)
                except ValueError:
                    raise ValueError(
                        "quick_deep_dive_duration_minutes must be a positive integer"
                    ) from None
                if minutes <= 0:
                    raise ValueError(
                        "quick_deep_dive_duration_minutes must be a positive integer"
                    )
            normalized["quick_deep_dive_duration_minutes"] = value

        presets = normalized.get("quick_deep_dive_host_presets")
        if presets is not None:
            parsed = tuple(item.strip() for item in presets.split(",") if item.strip())
            if parsed and (len(parsed) != 2 or any(item not in _HOST_PRESETS for item in parsed)):
                raise ValueError(
                    "quick_deep_dive_host_presets must contain exactly two valid host presets"
                )
            normalized["quick_deep_dive_host_presets"] = ",".join(parsed)

        local_only = normalized.get("local_only")
        if local_only is not None:
            value = local_only.strip().lower()
            if value and value not in _BOOLEAN_DEFAULTS:
                raise ValueError("local_only must be a boolean value")
            normalized["local_only"] = value
        return normalized

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


class UserConfigConflictError(UserConfigError):
    """Raised instead of silently overwriting a config changed by another writer."""


class UserConfigStore:
    """JSON-backed user config with atomic publication and stale-writer detection.

    The parent directory is assumed to be owned/trusted by the current user. Files
    created by this store never follow a config or temporary-file symlink.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> UserConfig:
        with self._locked():
            return self._load_unlocked()

    def _load_unlocked(self) -> UserConfig:
        if self.path.is_symlink():
            raise UserConfigError(f"invalid user configuration path at {self.path}")
        if not self.path.exists():
            return UserConfig()
        try:
            raw_bytes = self.path.read_bytes()
            raw = raw_bytes.decode("utf-8")
            config = UserConfig.model_validate_json(raw)
            config._revision = self._revision(raw_bytes)
            return config
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
        except (OSError, UnicodeError, ValueError):
            raise UserConfigError(f"invalid user configuration at {self.path}") from None

    def save(self, config: UserConfig) -> None:
        # Pydantic models are mutable by default. Revalidate the whole candidate
        # before taking the filesystem mutation path.
        try:
            validated = UserConfig.model_validate(config.model_dump(mode="python"))
        except ValidationError as exc:
            location = ", ".join(
                ".".join(map(str, err["loc"])) or "configuration"
                for err in exc.errors(include_input=False, include_url=False)
            )
            raise UserConfigError(f"invalid user configuration: check {location}") from None

        payload = (
            json.dumps(validated.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with self._locked():
            if self.path.is_symlink():
                raise UserConfigError(f"invalid user configuration path at {self.path}")
            current_revision = self._current_revision()
            if config._revision is not None and current_revision != config._revision:
                raise UserConfigConflictError(
                    "user configuration changed since it was loaded; reload and retry"
                )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._write_temporary(payload)
            replaced = False
            try:
                os.replace(temporary, self.path)
                replaced = True
                self._restrict_permissions(self.path)
                self._sync_parent_directory()
            finally:
                if not replaced:
                    temporary.unlink(missing_ok=True)
            config._revision = self._revision(payload)

    def _write_temporary(self, payload: bytes) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                if os.name == "posix":
                    os.fchmod(handle.fileno(), 0o600)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            return temporary
        except Exception:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise

    def _current_revision(self) -> str | None:
        if not self.path.exists():
            return None
        return self._revision(self.path.read_bytes())

    @staticmethod
    def _revision(payload: bytes) -> str:
        return sha256(payload).hexdigest()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        key = str(self.path.absolute())
        with _PATH_LOCKS_GUARD:
            process_lock = _PATH_LOCKS.setdefault(key, RLock())
        with process_lock:
            lock_handle = self._open_advisory_lock()
            try:
                yield
            finally:
                if lock_handle is not None:
                    if fcntl is not None:
                        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    lock_handle.close()

    def _open_advisory_lock(self) -> IO[bytes] | None:
        if fcntl is None:
            return None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.parent / f".{self.path.name}.lock"
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(lock_path, flags, 0o600)
        handle = os.fdopen(descriptor, "r+b", closefd=True)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except Exception:
            handle.close()
            raise
        return handle

    def _sync_parent_directory(self) -> None:
        if os.name != "posix" or not hasattr(os, "O_DIRECTORY"):
            return
        descriptor = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _restrict_permissions(path: Path) -> None:
        if os.name == "posix":
            path.chmod(0o600)
