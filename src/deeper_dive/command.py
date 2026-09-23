"""Top-level CLI router including provider automation commands."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from deeper_dive import cli
from deeper_dive.composition import ProductionComposition
from deeper_dive.kitten_model_manager import KittenModelManager, KittenModelState
from deeper_dive.kitten_tts import KittenTTSMicroProvider
from deeper_dive.provider_tui import ProviderController
from deeper_dive.storage.workspace import WorkspaceManager
from deeper_dive.tts_benchmark import TTSBenchmarkService
from deeper_dive.user_errors import actionable_error


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
        return _delegated_cli(values, args)
    try:
        return _provider(args)
    except (KeyError, OSError, RuntimeError, ValueError) as exc:
        import sys

        area = _provider_error_area(args.provider_command)
        print(actionable_error(area, exc).message, file=sys.stderr)
        return 2


def _delegated_cli(values: list[str] | None, args: argparse.Namespace) -> int:
    import contextlib
    import io
    import sys

    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = cli.main(values)
    diagnostic = stderr.getvalue().strip()
    if code != 0 and diagnostic:
        error = actionable_error(_cli_error_area(args), RuntimeError(diagnostic))
        print(error.message, file=sys.stderr)
    elif diagnostic:
        print(diagnostic, file=sys.stderr)
    return code


def _cli_error_area(args: argparse.Namespace) -> str:
    command = getattr(args, "command", "")
    if command == "source":
        return "network" if getattr(args, "url", False) else "parser"
    if command == "research":
        return "network"
    if command == "host" and getattr(args, "host_command", "") == "voice":
        return "tts"
    return "operation"


def _provider_error_area(provider_command: str | None) -> str:
    if provider_command in {"voices", "kitten-install", "kitten-benchmark"}:
        return "tts"
    return "provider"


def _provider(args: argparse.Namespace) -> int:
    composition = ProductionComposition.build(data_dir=args.data_dir)
    workspace = composition.service.workspaces
    config = composition.config_store.load()
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
        return _output(
            _inspect_provider(composition.provider_controller, command, args.provider_id),
            args.json_output,
        )
    if command in {"kitten-status", "kitten-install", "kitten-benchmark"}:
        return _output(
            _kitten(command, workspace, args, composition.benchmark_service),
            args.json_output,
        )
    raise ValueError(
        "provider command must be list, health, test, models, voices, "
        "kitten-status, kitten-install, or kitten-benchmark"
    )


def _inspect_provider(
    controller: ProviderController, command: str, provider_id: str | None
) -> object:
    if provider_id is None:
        raise ValueError(f"provider id is required for {command}")
    provider_config = controller.config().providers.get(provider_id)
    if provider_config is None:
        raise KeyError(f"unknown provider: {provider_id}")
    capability = controller.capability(provider_config.provider_type)
    if command == "models":
        if capability != "llm":
            raise ValueError(f"provider {provider_id!r} does not support model discovery")
        return [asdict(model) for model in controller.llm(provider_id).models()]
    if command == "voices":
        if capability != "tts":
            raise ValueError(f"provider {provider_id!r} does not support voice discovery")
        return [asdict(voice) for voice in controller.tts(provider_id).voices()]
    if command in {"health", "test"}:
        if capability == "llm":
            llm = controller.llm(provider_id)
            return {"id": llm.provider_id, **asdict(llm.health())}
        if capability == "tts":
            tts = controller.tts(provider_id)
            return {"id": tts.provider_id, **asdict(tts.health())}
        raise ValueError(f"provider {provider_id!r} has unsupported adapter capability")
    raise ValueError(f"provider {provider_id!r} does not support {command}")


def _kitten(
    command: str,
    workspace: WorkspaceManager,
    args: argparse.Namespace,
    benchmark_service: TTSBenchmarkService,
) -> object:
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
    voices = provider.voices()
    if not voices:
        raise RuntimeError("KittenTTS provider has no benchmark voice")
    result = benchmark_service.run(
        provider,
        voice=voices[0].id,
        model=state.model_id if state.installed else None,
    )
    return {"installed": state.installed, **asdict(result)}


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
