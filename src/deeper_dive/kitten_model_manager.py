"""On-demand KittenTTS model installation and lifecycle management."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from deeper_dive.kitten_tts import MICRO_MODEL_ID

Fetcher = Callable[[str, Path], None]


@dataclass(frozen=True)
class KittenModelState:
    model_id: str
    version: str
    path: Path
    installed: bool
    sha256: str | None = None


def _fetch(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


class KittenModelManager:
    """Manage separately downloaded KittenTTS weights without bundling them in the package."""

    def __init__(self, model_dir: Path, *, fetcher: Fetcher | None = None) -> None:
        self.model_dir = Path(model_dir)
        self._fetcher = fetcher or _fetch

    def state(self) -> KittenModelState:
        manifest = self._read_manifest()
        artifact = self.model_dir / "model.bin"
        installed = bool(manifest and artifact.is_file())
        return KittenModelState(
            model_id=str(manifest.get("model_id", MICRO_MODEL_ID)) if manifest else MICRO_MODEL_ID,
            version=str(manifest.get("version", "unknown")) if manifest else "unknown",
            path=artifact,
            installed=installed,
            sha256=str(manifest["sha256"]) if manifest and manifest.get("sha256") else None,
        )

    def install(
        self,
        *,
        url: str,
        version: str,
        sha256: str | None = None,
    ) -> KittenModelState:
        """Download atomically; an interrupted/invalid download is never considered installed."""
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_partials()
        fd, temporary_name = tempfile.mkstemp(prefix="model.", suffix=".partial", dir=self.model_dir)
        os.close(fd)
        partial = Path(temporary_name)
        try:
            self._fetcher(url, partial)
            if not partial.is_file() or partial.stat().st_size == 0:
                raise RuntimeError("KittenTTS model download produced an empty artifact")
            digest = _sha256(partial)
            if sha256 is not None and digest.lower() != sha256.lower():
                raise RuntimeError("KittenTTS model download failed SHA-256 integrity verification")
            artifact = self.model_dir / "model.bin"
            partial.replace(artifact)
            self._write_manifest(
                {"model_id": MICRO_MODEL_ID, "version": version, "sha256": digest}
            )
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        return self.state()

    def uninstall(self) -> None:
        (self.model_dir / "model.bin").unlink(missing_ok=True)
        (self.model_dir / "manifest.json").unlink(missing_ok=True)
        self._cleanup_partials()

    def reinstall(self, *, url: str, version: str, sha256: str | None = None) -> KittenModelState:
        self.uninstall()
        return self.install(url=url, version=version, sha256=sha256)

    def _cleanup_partials(self) -> None:
        if self.model_dir.exists():
            for path in self.model_dir.glob("*.partial"):
                path.unlink(missing_ok=True)

    def _read_manifest(self) -> dict[str, object] | None:
        path = self.model_dir / "manifest.json"
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    def _write_manifest(self, value: dict[str, object]) -> None:
        path = self.model_dir / "manifest.json"
        temporary = path.with_suffix(".json.partial")
        temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
