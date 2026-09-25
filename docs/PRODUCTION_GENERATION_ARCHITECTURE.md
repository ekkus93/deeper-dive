# Production generation architecture

This note documents the developer-facing contracts behind provider-backed production generation. It complements `docs/ARCHITECTURE.md`, `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md`, and `docs/GENERATION_RUN_SELECTION_POLICY.md`.

## Shared generation start service

`GenerationStartService` is the shared CLI/TUI readiness and run-selection boundary. Product surfaces should call it before starting generation instead of creating runs directly.

Responsibilities:

- build a preflight report using the production `PreflightService`;
- enforce blockers before creating or reusing a run;
- apply the duplicate-safe generation run policy;
- select the durable run that the monitor, CLI status/control commands, and Episode Library actions should target;
- surface sanitized, actionable errors when readiness fails.

The CLI `episode generate` path and the TUI Generate screen are expected to share this boundary. Surface-specific code may format the result differently, but should not implement a separate readiness matrix.

## Provider-backed generation stage contracts

Production stages must resolve provider/model assignments through durable configuration and provider registries.

- Planning uses `EpisodePlannerService` with a configured LLM provider/model.
- Conversation generation uses the configured `host_generation` role and optional configured `directing` role.
- Verification uses the configured `verification` role when present.
- Generated host turns are persisted through `HostTurnService` with transcript/evidence data and provider/model identity where supplied.
- Malformed structured provider output fails before downstream audio output is produced and must be reported through sanitized diagnostics.

Deterministic fake providers are valid only as explicitly configured provider adapters. Do not add hidden deterministic production paths that bypass the provider factory/registry boundary.

## Provider-backed TTS stage contracts

The TTS stage resolves every generated turn through the selected host's configured provider and voice. Missing host TTS assignment, unknown providers, unknown voices, empty provider audio, and provider/runtime failures should fail through actionable, sanitized errors.

TTS generation writes durable artifacts through `TTSArtifactRepository` and `TTSGenerationStage`. Reuse is cache-key based and valid only when the cached artifact is successful, exists on disk, and is non-empty. Transcript repair or other text-changing operations must invalidate affected audio or force regeneration through the same artifact contract.

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
