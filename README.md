# Deeper Dive

Deeper Dive is a terminal-first, local-friendly application for turning a collection of documents into evidence-grounded research conversations and generated multi-host audio deep dives. It is designed for private project workspaces, explicit provider routing, inspectable source provenance, durable generation checkpoints, and fake-provider automation in normal CI.

The design authority is [`docs/DEEP_DIVE_TUI_SPEC.md`](docs/DEEP_DIVE_TUI_SPEC.md). The ordered implementation and qualification plan is [`docs/DEEP_DIVE_TUI_TODO.md`](docs/DEEP_DIVE_TUI_TODO.md). Provider setup is documented in [`docs/PROVIDERS.md`](docs/PROVIDERS.md), research/provenance behavior is documented in [`docs/RESEARCH_PROVENANCE.md`](docs/RESEARCH_PROVENANCE.md), developer architecture notes are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), and privacy/security behavior is in [`docs/PRIVACY_SECURITY.md`](docs/PRIVACY_SECURITY.md).

## Current interface

Deeper Dive ships both a Textual TUI and a JSON-capable CLI. The UI is still stabilizing, so this README uses a terminal capture instead of screenshots.

```text
Projects  Providers  Settings  Help
Sources   Research   Hosts     Episode   Generate   Library

Typical workflow:
1. Create or open a project.
2. Add source documents or explicit URLs.
3. Optional: analyze research gaps and add supplemental sources.
4. Configure hosts and voices.
5. Configure and plan an episode.
6. Run preflight to review provider routing, blockers, warnings, FFmpeg, and estimates.
7. Generate, review transcript/claims/audio, and export artifacts.
```

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- FFmpeg for audio composition/export
- Optional local LLM runtime such as Ollama or llama-server
- Optional KittenTTS Micro runtime for local CPU speech
- Optional cloud credentials only when you choose cloud providers

Importing `deeper_dive` is intentionally side-effect free: it does not contact providers, access the network, or download models.

## Install for development

```bash
uv sync --frozen
```

Run the complete local quality gate with:

```bash
./scripts/check.sh
```

That command checks formatting, Ruff lint, strict mypy typing, and pytest. Each stage exits nonzero on failure.

## Run

```bash
uv run deeper-dive --help
uv run deeper-dive --version
uv run deeper-dive-tui
```

The CLI supports JSON output for automation:

```bash
uv run deeper-dive --json project create "My Deep Dive"
uv run deeper-dive --json project list
```

## First-run flow

The first-run readiness path is intentionally cloud-optional. It guides the user through:

- FFmpeg detection for audio assembly.
- KittenTTS Micro availability for local CPU speech.
- Provider setup guidance.
- Local-only viability using local provider configuration.
- Skipping cloud provider configuration.
- Creating an empty project and adding user-owned sources.

No copyrighted sample corpus is bundled. Start with an empty project and import your own documents.

## Local-only example

A local-only workflow can use local LLM and TTS providers without cloud credentials. The exact provider configuration depends on your local runtime, but the intended shape is:

```bash
uv run deeper-dive-tui
# Open Providers.
# Add a local LLM provider such as Ollama or llama-server.
# Add or use a local TTS provider such as KittenTTS Micro.
# Open Generate/Preflight and verify provider routes are local before generation.
```

The preflight screen distinguishes local and remote provider routes and warns when source text may be sent to a remote provider. Local-only mode is intended to block remote routes before expensive generation begins.

## Cloud-provider example

Cloud providers are optional and must be configured deliberately. A cloud-backed workflow generally looks like this:

```bash
uv run deeper-dive-tui
# Open Providers.
# Add an LLM provider with its endpoint/model settings.
# Configure credentials through the supported secret/environment mechanism.
# Add a TTS provider if you want cloud speech.
# Run preflight and review exactly which stages send content to each provider.
```

Provider credentials are not stored in normal project databases, exported metadata, or diagnostic bundles by default. See [`docs/PROVIDERS.md`](docs/PROVIDERS.md) for provider-specific setup.

## Core concepts

- **Project**: an isolated workspace containing sources, indexes, episodes, runs, transcripts, and exports.
- **Source**: a user-supplied or supplemental document with retained origin/provenance.
- **Supplemental research**: gap-driven web research that remains distinguishable from primary user sources.
- **Host**: an editable participant profile with role, traits, relationships, and optional TTS voice assignment.
- **Episode**: a configured deep dive with focus, audience, duration, hosts, research policy, and model overrides.
- **Plan**: a structured segment plan generated before dialogue/TTS begins.
- **Run**: a durable generation execution with checkpointed stages, pause/resume/cancel state, and diagnostics.
- **Export**: generated audio, transcript, source manifest, and metadata artifacts.

## CLI automation overview

Representative commands:

```bash
uv run deeper-dive --json project create "Demo"
uv run deeper-dive --json source add <project-id> ./docs
uv run deeper-dive --json host presets
uv run deeper-dive --json episode create <project-id> --title "Demo" --hosts <host-id>
uv run deeper-dive --json episode plan <project-id> <episode-id>
uv run deeper-dive --json episode generate <project-id> <episode-id>
uv run deeper-dive --json episode status <project-id> <episode-id>
uv run deeper-dive --json episode export <project-id> <episode-id>
```

Normal CI uses deterministic fake providers and fixtures. Live providers, live web search, GPU hardware, and model downloads are not required for ordinary test runs.

## Development status

The project is under active implementation. Use [`docs/DEEP_DIVE_TUI_SPEC.md`](docs/DEEP_DIVE_TUI_SPEC.md) for the product/design contract and [`docs/DEEP_DIVE_TUI_TODO.md`](docs/DEEP_DIVE_TUI_TODO.md) for task ordering and qualification state.
