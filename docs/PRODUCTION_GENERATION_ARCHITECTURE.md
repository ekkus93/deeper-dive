# Production generation architecture

This note documents the developer-facing contracts behind provider-backed production generation. It complements `docs/ARCHITECTURE.md`, `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md`, `docs/GENERATION_RUN_SELECTION_POLICY.md`, and the follow-up remediation spec `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_SPEC_2026-09-25.md`.

## Shared generation start service

`GenerationStartService` is the shared CLI/TUI readiness and run-selection boundary. Product surfaces should call it before starting generation instead of creating runs directly.

Responsibilities:

- build a preflight report using the production `PreflightService`;
- enforce blockers before creating or reusing a run;
- apply the duplicate-safe generation run policy;
- select the durable run that the monitor, CLI status/control commands, and Episode Library actions should target;
- surface sanitized, actionable errors when readiness fails.

The CLI `episode generate` path and the TUI Generate screen are expected to share this boundary. Surface-specific code may format the result differently, but should not implement a separate readiness matrix.

## Runtime provider refresh boundary

`ProductionComposition`, `ProviderController`, `PreflightService`, and the LLM/TTS provider registries share one refresh/access boundary. Same-session provider saves, removals, and reloads must atomically refresh the production registries consumed by preflight, planning, conversation generation, TTS generation, provider health, and export/composition. A surface may inject or attach a provider controller, but it must not leave a stale `ProductionComposition.providers` snapshot behind after the controller reloads.

Credential values remain secret material. Provider refresh must preserve credential non-persistence and must route status, diagnostics, CLI/TUI messages, metadata, logs, and exports through the sanitizer/redaction boundary before user-visible or durable output is written.

## Provider-backed generation stage contracts

Production stages must resolve provider/model assignments through durable configuration and provider registries.

- Planning uses `EpisodePlannerService` with a configured `episode_planning` LLM provider/model resolved through the same user > project > episode precedence as CLI `episode plan`.
- Conversation generation uses the configured `host_generation` role and optional configured `directing` role.
- Verification uses the configured `verification` role when present.
- Generated host turns are persisted through `HostTurnService` with transcript/evidence data and provider/model identity where supplied.
- Malformed structured provider output fails before downstream audio output is produced and must be reported through sanitized diagnostics.

Pipeline auto-planning must never fall back to the first sorted provider/model when a configured planning assignment is required. Missing assignments, unknown providers, unavailable models, provider exceptions, invalid JSON, empty segment output, and unhealthy planning providers are terminal planning failures for the durable run. These failures must stop before conversation, TTS, or composition stages and must be exposed consistently through CLI `episode generate`, TUI Generate/preflight, and monitor/background generation.

Deterministic fake providers are valid only as explicitly configured provider adapters. Do not add hidden deterministic production paths that bypass the provider factory/registry boundary.

## Evidence and generated provenance contracts

Provider-backed directing and host-turn generation receive an explicit evidence scope derived from durable episode planning and indexed source chunks. The supplied evidence IDs must be valid for the current project and episode scope. Provider-returned citations outside that supplied scope are rejected rather than persisted.

Valid generated evidence IDs are persisted on transcript turns. Export resolves those citations back to source passage metadata and text so transcript markdown, provenance manifests, and review/export surfaces can show the generated claim/citation relationship without manually seeded turn provenance. Multi-project and multi-episode isolation is part of the evidence contract: one project or episode must not leak plan evidence into another generation run.

## Provider-backed TTS stage contracts

The TTS stage resolves every generated turn through the selected host's configured provider and voice. Missing host TTS assignment, unknown providers, unknown voices, empty provider audio, and provider/runtime failures should fail through actionable, sanitized errors.

TTS generation writes durable artifacts through `TTSArtifactRepository` and `TTSGenerationStage`. Reuse is cache-key based and valid only when the cached artifact is successful, exists on disk, and is non-empty. The cache key includes text, provider, voice, model, response format, and non-default synthesis settings, so transcript repair or provider/voice/model/settings changes force the affected turn through regeneration.

`tts_artifacts` is a per-turn artifact-reference table. Every generated turn has its own persisted row. Multiple turns may intentionally share the same `cache_key`, `artifact_id`, and filesystem path when synthesis input is identical; the cache key is therefore indexed but not unique. This preserves per-turn lookup while allowing duplicate speech to reuse one physical artifact. Provider-returned format and provider/voice/model metadata are recorded from the actual synthesis result, and the stored format matches the artifact filename extension.

Provider-configured response format must be threaded into production synthesis requests. OpenAI-compatible TTS configured for `mp3` must receive `response_format="mp3"` and produce matching metadata/extension records. WAV-only providers such as KittenTTS Micro must reject unsupported response formats before recording success.

## Audio composition contracts

Production episode audio composition operates on resolved per-turn TTS artifact references, not raw byte concatenation. Supported WAV artifacts are validated, normalized, ordered by transcript turn/timeline identity, and written through `EpisodeExporter.write_wav()` so the final episode `.wav` has one coherent header and combined PCM frames.

Compressed/container artifacts, including MP3, are not composed in this follow-up path unless a future FFmpeg-backed composition service explicitly supports them. Missing, empty, unreadable, unsupported, compressed/container, or mismatched TTS artifacts must fail with sanitized actionable diagnostics before composition is marked complete.

## Stage boundary and export semantics

`PipelineOrchestrator` owns durable stage transitions, completed-unit checkpoints, pause/cancel boundaries, retry behavior, and failure state. Some stages are intentional durable readiness/checkpoint boundaries rather than file-writing stages.

The generation pipeline `export` stage means generation is ready for explicit export. Concrete export files are created by CLI export or Episode Library export through the export service. Tests must not treat pipeline `export` completion alone as proof that transcript, manifest, metadata, or audio export files were written.

## TTS artifact status compatibility

The canonical successful TTS artifact status is `complete`. The legacy success value `completed` remains readable for compatibility and is normalized by `TTSArtifactRepository`. New writes must use `complete` only.

Repository-level compatibility tests should prove:

- legacy successful rows are normalized to the canonical status;
- cache lookup accepts legacy success rows after normalization;
- exports and timelines continue to load previously generated artifacts when their files exist;
- no production writer emits a noncanonical success status after remediation.

## Persisted data compatibility policy

Project databases and user configuration should be forward-safe within the supported schema version. Existing provider records that use current concrete adapter types must load with defaults for newly added optional fields. Ambiguous generic legacy provider entries such as `llm` or `tts` are unsafe to migrate automatically and must be rejected with guidance to choose a concrete adapter type.

Existing episodes, runs, transcript turns, provider identity rows, audio timelines, and TTS artifacts must remain loadable through repositories after new generation semantics land. Compatibility tests should create or emulate older persisted rows and then load them through the current repositories/services rather than relying only on fixture JSON comparisons.

## Deterministic provider-boundary testing strategy

Normal CI uses configured fake LLM/TTS adapters to exercise the same production boundaries used by real adapters. Acceptance fixtures should build a real project workspace, configure providers through `UserConfigStore`, create sources, hosts, an episode, a plan, a run, generated turns, TTS artifacts, and exports, then assert repository state and exported files.

Live-provider, network, GPU, paid-credential, and model-download tests must remain opt-in or isolated from ordinary CI. Fresh-machine checks may install optional local CPU runtimes such as KittenTTS as a bounded separate qualification step.
