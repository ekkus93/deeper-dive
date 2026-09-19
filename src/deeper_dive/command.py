"""Top-level CLI router including provider automation commands."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from deeper_dive import cli
from deeper_dive.kitten_model_manager import KittenModelManager, KittenModelState
from deeper_dive.kitten_tts import KittenTTSMicroProvider
from deeper_dive.llm import FakeLLMProvider
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts import FakeTTSProvider
from deeper_dive.user_config import UserConfigStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("command", nargs="?")
    parser.add_argument("provider_command", nargs="?")
    parser.add_argument("provider_id", nargs="?")
    parser.add_argument("--url")
    parser.add_argument("--version", dest="model_version")
    parser.add_argument("--sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv) if argv is not None else None
    args, _ = _parser().parse_known_args(values)
    if args.command != "provider":
        return cli.main(values)
    try:
        return _provider(args)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        import sys

        print(str(exc), file=sys.stderr)
        return 2


def _provider(args: argparse.Namespace) -> int:
    workspace = WorkspaceManager(args.data_dir)
    workspace.initialize()
    config = UserConfigStore(workspace.data_dir / "config.json").load()
    command = args.provider_command
    if command == "list":
        return _output(
            [
                {"id": name, **provider.model_dump(mode="json")}
                for name, provider in sorted(config.providers.items())
            ],
            args.json_output,
        )
    if command in {"health", "test", "models", "voices"}:
        return _output(_inspect_provider(command, args.provider_id), args.json_output)
    if command in {"kitten-status", "kitten-install", "kitten-benchmark"}:
        return _output(_kitten(command, workspace, args), args.json_output)
    raise ValueError(
        "provider command must be list, health, test, models, voices, "
        "kitten-status, kitten-install, or kitten-benchmark"
    )


def _inspect_provider(command: str, provider_id: str | None) -> object:
    if provider_id in {None, "fake"}:
        llm = FakeLLMProvider()
        if command in {"health", "test"}:
            return {"id": llm.provider_id, **asdict(llm.health())}
        if command == "models":
            return [asdict(model) for model in llm.models()]
    if provider_id in {"fake-tts", "kitten"}:
        tts = FakeTTSProvider() if provider_id == "fake-tts" else KittenTTSMicroProvider()
        if command in {"health", "test"}:
            return {"id": tts.provider_id, **asdict(tts.health())}
        if command == "voices":
            return [asdict(voice) for voice in tts.voices()]
    raise ValueError(f"provider {provider_id!r} does not support {command}")


def _kitten(command: str, workspace: WorkspaceManager, args: argparse.Namespace) -> object:
    manager = KittenModelManager(workspace.models_dir / "kitten")
    if command == "kitten-install":
        if not args.url or not args.model_version:
            raise ValueError("kitten-install requires --url and --version")
        state = manager.install(url=args.url, version=args.model_version, sha256=args.sha256)
        return _state(state)
    state = manager.state()
    if command == "kitten-status":
        return _state(state)
    provider = KittenTTSMicroProvider()
    health = provider.health()
    return {
        "installed": state.installed,
        "runtime_healthy": health.healthy,
        "message": health.message,
        "voice_count": len(provider.voices()),
        "sample_rate_hz": 24000,
    }


def _state(state: KittenModelState) -> dict[str, object]:
    return {
        "model_id": state.model_id,
        "version": state.version,
        "path": str(state.path),
        "installed": state.installed,
        "sha256": state.sha256,
    }


def _output(value: object, json_output: bool) -> int:
    if json_output:
        print(json.dumps(value, sort_keys=True))
    elif isinstance(value, list):
        for item in value:
            print(json.dumps(item, sort_keys=True))
    else:
        print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
