"""Versioned non-secret user configuration stored outside project workspaces."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from hashlib import sha256
from pathlib import Path
from threading import Lock, RLock
from typing import IO, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    ValidationError,
    ValidationInfo,
    field_validator,
)

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
_MODEL_ROLE_DEFAULTS = frozenset(
    {
        "corpus_analysis",
        "research_planning",
        "source_analysis",
        "episode_planning",
        "directing",
        "host_generation",
        "verification",
    }
)
_NETWORK_POLICIES = frozenset(
    {"local-only", "configured-providers", "allow-remote", "remote-allowed"}
)
_DIAGNOSTIC_LOGGING = frozenset({"off", "normal", "verbose"})
_SPEECH_SETUP = frozenset({"configured", "deferred"})
_PATH_DEFAULTS = frozenset({"ffmpeg_executable", "kitten_model_dir"})


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
        # An empty trailing fragment delimiter is still a fragment and should
        # never be persisted as part of a provider endpoint.
        if "#" in value:
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
    _legacy_model_role_defaults: dict[str, str] = PrivateAttr(default_factory=dict)
    schema_version: int = CURRENT_CONFIG_VERSION
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)

    @field_validator("defaults")
    @classmethod
    def validate_defaults(
        cls,
        values: dict[str, str],
        info: ValidationInfo,
    ) -> dict[str, str]:
        normalized = dict(values)
        context = info.context if isinstance(info.context, dict) else {}
        legacy_roles = context.get("legacy_model_role_defaults", {})
        if not isinstance(legacy_roles, dict):
            legacy_roles = {}
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
                    raise ValueError("quick_deep_dive_duration_minutes must be a positive integer")
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

        network = normalized.get("network_policy")
        if network is not None:
            value = network.strip().lower().replace("_", "-").replace(" ", "-")
            if value and value not in _NETWORK_POLICIES:
                raise ValueError(
                    "network_policy must be one of: " + ", ".join(sorted(_NETWORK_POLICIES))
                )
            normalized["network_policy"] = value

        diagnostic = normalized.get("diagnostic_logging")
        if diagnostic is not None:
            value = diagnostic.strip().lower()
            if value and value not in _DIAGNOSTIC_LOGGING:
                raise ValueError(
                    "diagnostic_logging must be one of: " + ", ".join(sorted(_DIAGNOSTIC_LOGGING))
                )
            normalized["diagnostic_logging"] = value

        speech_setup = normalized.get("speech_setup")
        if speech_setup is not None:
            value = speech_setup.strip().lower()
            if value and value not in _SPEECH_SETUP:
                raise ValueError("speech_setup must be configured or deferred")
            normalized["speech_setup"] = value

        for key in _PATH_DEFAULTS:
            raw = normalized.get(key)
            if raw is None:
                continue
            value = raw.strip()
            if "\x00" in value or "\n" in value or "\r" in value:
                raise ValueError(f"{key} must be a single filesystem path or executable name")
            normalized[key] = value

        local_ids = normalized.get("local_provider_ids")
        if local_ids is not None:
            normalized["local_provider_ids"] = ",".join(
                item.strip() for item in local_ids.split(",") if item.strip()
            )

        for key in _MODEL_ROLE_DEFAULTS:
            raw = normalized.get(key)
            if raw is None:
                continue
            value = raw.strip()
            if value:
                provider, separator, model = value.partition(":")
                if not separator:
                    if legacy_roles.get(key) == value and re.fullmatch(r"[A-Za-z0-9_.-]+", value):
                        normalized[key] = value
                        continue
                    raise ValueError(f"{key} must use non-empty provider:model")
                if not provider.strip() or not model.strip():
                    raise ValueError(f"{key} must use non-empty provider:model")
                value = f"{provider.strip()}:{model.strip()}"
            normalized[key] = value

        for key in ("tts_provider", "tts_voice", "tts_voice_host_1", "tts_voice_host_2"):
            raw = normalized.get(key)
            if raw is not None:
                normalized[key] = raw.strip()
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
            payload = json.loads(raw)
            legacy_roles = self._legacy_model_role_defaults(payload)
            config = UserConfig.model_validate(
                payload,
                context={"legacy_model_role_defaults": legacy_roles},
            )
            config._revision = self._revision(raw_bytes)
            config._legacy_model_role_defaults = legacy_roles
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

    @staticmethod
    def validate_candidate(config: UserConfig) -> UserConfig:
        """Revalidate mutable models before any provider build or filesystem effects."""
        try:
            return UserConfig.model_validate(
                config.model_dump(mode="python"),
                context={"legacy_model_role_defaults": dict(config._legacy_model_role_defaults)},
            )
        except ValidationError as exc:
            location = ", ".join(
                ".".join(map(str, err["loc"])) or "configuration"
                for err in exc.errors(include_input=False, include_url=False)
            )
            raise UserConfigError(f"invalid user configuration: check {location}") from None

    def save(self, config: UserConfig) -> None:
        validated = self.validate_candidate(config)
        payload = (
            json.dumps(validated.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with self._locked():
            if self.path.is_symlink():
                raise UserConfigError(f"invalid user configuration path at {self.path}")
            current_revision = self._current_revision()
            if current_revision != config._revision:
                raise UserConfigConflictError(
                    "user configuration changed since it was loaded; reload and retry"
                )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._write_temporary(payload)
            replaced = False
            try:
                # Permissions must be finalized before publication. A chmod
                # failure after os.replace would expose new bytes while falsely
                # reporting a failed pre-publication transaction.
                self._restrict_permissions(temporary)
                os.replace(temporary, self.path)
                replaced = True
                # Publication has already happened even if the following directory
                # fsync reports uncertain crash durability. Keep this in-memory
                # revision aligned with the bytes now visible on disk.
                config._revision = self._revision(payload)
                self._sync_parent_directory()
            finally:
                if not replaced:
                    self._cleanup_temporary(temporary)

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
                self._cleanup_temporary(temporary)
            raise

    @staticmethod
    def _cleanup_temporary(temporary: Path) -> None:
        """Best-effort removal of an owned temp without masking the write error.

        A cleanup failure cannot undo a failed write; callers retain the original
        failure so it can be diagnosed instead of reporting a misleading unlink.
        """
        with suppress(OSError):
            temporary.unlink(missing_ok=True)

    def _current_revision(self) -> str | None:
        if not self.path.exists():
            return None
        return self._revision(self.path.read_bytes())

    @staticmethod
    def _legacy_model_role_defaults(payload: object) -> dict[str, str]:
        if not isinstance(payload, dict):
            return {}
        defaults = payload.get("defaults")
        if not isinstance(defaults, dict):
            return {}
        legacy: dict[str, str] = {}
        for key in _MODEL_ROLE_DEFAULTS:
            value = defaults.get(key)
            if not isinstance(value, str):
                continue
            cleaned = value.strip()
            if cleaned and ":" not in cleaned and re.fullmatch(r"[A-Za-z0-9_.-]+", cleaned):
                legacy[key] = cleaned
        return legacy

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
