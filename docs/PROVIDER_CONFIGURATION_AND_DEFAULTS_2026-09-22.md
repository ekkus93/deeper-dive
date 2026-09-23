# Provider Configuration and Defaults

**Related remediation items:** DDR-070, DDR-071, DDR-072, DDR-073, DDR-074, DDR-106, DDR-120, DDR-121, DDR-122, DDR-140

This document records the V1 provider configuration contract that the CLI, TUI, preflight, planning, generation, discovery, health checks, TTS synthesis, and benchmark surfaces must share.

The intent is to keep provider behavior centralized in the production composition path rather than in screen-specific or command-specific shortcuts.

## Provider identity model

Persisted provider records must use concrete adapter identities, not generic capability labels.

Supported LLM provider types are:

- `fake` for deterministic CI and local development tests.
- `openai` for OpenAI-style hosted LLMs.
- `ollama` for local Ollama models.
- `llama-server` for OpenAI-compatible local llama-server endpoints.

Supported TTS provider types are:

- `fake-tts` for deterministic CI and local development tests.
- `kitten` for local KittenTTS synthesis.
- `openai-tts` for OpenAI TTS.
- `openai-compatible-tts` for compatible HTTP TTS endpoints.
- `elevenlabs` for ElevenLabs-style hosted TTS.

Legacy generic provider types such as `llm` and `tts` are intentionally ambiguous. They must either be normalized by a safe migration or rejected with actionable guidance.

## Production construction path

All provider-facing surfaces should be constructed through `ProductionComposition.build(...)` and the shared provider factory/registries.

The shared construction path is responsible for:

- Loading durable user configuration from `UserConfigStore`.
- Building configured providers through `ProviderFactory`.
- Registering LLM providers in the shared LLM registry.
- Registering TTS providers in the shared TTS registry.
- Preserving provider network-scope metadata.
- Providing the same provider controller to TUI and CLI surfaces.
- Surfacing sanitized configuration errors.

TUI screens and CLI commands should consume these shared objects. They should not silently instantiate alternate provider registries or hard-coded providers outside explicit test/development injection seams.

## Default precedence

Effective model/default resolution follows this order:

1. Episode-level overrides.
2. Project-level defaults.
3. User/application defaults.
4. Explicit built-in fallback only where the feature contract permits one.

Preflight and generation must consume the same resolved assignments. A preflight report is only meaningful if it discloses the exact provider/model assignments that generation will use.

## Quick Deep Dive defaults

Quick Deep Dive is allowed to provide convenience defaults, but those defaults must flow into normal durable episode configuration.

The durable Quick Deep Dive path must retain these built-in fallbacks only when no configured default or project override replaces them:

- Curious Explainer + Skeptic hosts.
- Approximately 20-minute target duration.
- Useful research policy.

Once the Quick Deep Dive episode exists, planning, preflight, generation, review, playback, and export should treat it as a normal episode.

## Health and discovery surfaces

Provider health, model discovery, and voice discovery commands must operate on configured provider records.

A command should distinguish:

- A provider that is configured and healthy.
- A provider that is configured but unhealthy.
- A provider that cannot be constructed because of configuration or credential problems.
- A provider type that does not support a requested capability.

JSON output should be structured enough for tests and scripts to distinguish these outcomes without scraping prose.

## Credential and network handling

Credential names may appear in actionable error messages when required, but raw credential values must not appear in CLI output, TUI output, diagnostics, persisted failure fields, logs, or debug/repr payloads.

Provider network-scope metadata must be preserved so preflight can disclose when source text, generated context, or speech text may leave the local machine.

Normal CI must use deterministic local fake providers and must not require paid credentials or live external services.

## TTS and benchmark contract

TTS provider resolution is host-specific. Each host requiring speech output must resolve both a configured TTS provider and a valid voice.

The KittenTTS benchmark command must route through the shared benchmark service or equivalent production boundary and report:

- Timed synthesis elapsed time.
- Output audio duration.
- Real-time factor or equivalent throughput.
- Model/runtime/voice context.

Install/status commands may remain separate from actual synthesis benchmarking, but a successful benchmark must prove synthesis happened rather than only reporting availability metadata.

## Qualification expectations

Provider work is not complete merely because a provider type exists in code. Completion evidence should show:

- Durable provider records are loaded.
- Configured providers are instantiated through the factory.
- Preflight sees the configured routes.
- CLI and TUI use the same registries/composition path.
- Health/discovery/benchmark behavior is tested with deterministic adapters.
- Credential-bearing failures are sanitized.
- No ordinary CI path requires paid credentials or live external services.

This document is supporting evidence only. It does not by itself complete any remediation checkbox; TODO reconciliation still requires merged production behavior, tests, exact-head CI, and explicit evidence for each checked item.
