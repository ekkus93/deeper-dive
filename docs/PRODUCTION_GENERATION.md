# Production generation, readiness, and compatibility

This guide explains the production generation path used by both the CLI and the Textual TUI. It is written for users configuring generation and for developers maintaining the provider-backed workflow.

## User-facing generation behavior

Production generation is provider-backed. Episode planning, directing, host-turn generation, transcript verification, and speech synthesis are routed through configured provider adapters. Deeper Dive should not rely on hidden canned transcript or audio shortcuts in normal production paths.

A typical durable generation flow is:

1. Configure providers in user configuration, not in a project database.
2. Add sources and verify that they are indexed.
3. Create hosts and assign TTS provider/voice pairs.
4. Create and plan an episode.
5. Run preflight from the CLI or TUI.
6. Start generation through the shared generation-start service.
7. Review the transcript and generated artifacts.
8. Export transcript, metadata, source manifest, and composed audio.

The CLI and TUI use the same readiness/start semantics. Both surfaces run preflight-equivalent checks before creating or reusing a run, and both reject missing sources, unindexed sources, missing hosts, missing model-role assignments, missing TTS assignments, unavailable providers/models/voices, and FFmpeg blockers before expensive generation begins.

## Deterministic CI and development providers

Deterministic providers are supported only as explicit configured provider adapters. Normal CI uses fake LLM and fake TTS providers so tests can run without cloud credentials, live network services, GPUs, or model downloads.

Use deterministic providers for tests, local demos, and reproducible acceptance workflows. Do not treat deterministic output as production evidence unless the deterministic adapter was deliberately configured through the same durable provider configuration path used by production adapters.

## Provider routes and preflight

Preflight summarizes which provider/model or provider/voice route will handle each generation stage. It also distinguishes local and remote routes so users can review whether source text, prompts, or generated speech text may leave the machine.

Generation should not start when preflight reports blockers. Warnings should be reviewed before generation, especially when a remote provider route is selected for source-bearing stages.

## Duplicate-safe run behavior

Generation start is duplicate-safe. If an episode already has an active pending, running, or paused run, repeated CLI `episode generate` calls and repeated TUI Generate clicks reuse that run instead of creating another attempt. Terminal completed, failed, or cancelled runs may create a new attempt according to the run-selection policy.

Pause, resume, cancel, status, Episode Library resume, and Episode Library export all target the intended durable run identity. See `docs/GENERATION_RUN_SELECTION_POLICY.md` for the detailed state matrix.

## TTS provider, voice, and audio artifact behavior

Every host that requires audio must have an explicit TTS provider and voice assignment. Production synthesis goes through the configured TTS provider registry and the shared TTS artifact/cache contract.

TTS artifacts use the canonical successful status `complete`. Existing legacy artifacts with the old successful status `completed` are normalized when read or saved. Cache lookup, timeline rendering, and export accept compatible legacy successful artifacts but new writes should use only `complete`.

TTS artifact records retain provider ID, voice, model, cache key, and filesystem path. Transcript repair or other text changes must invalidate or regenerate affected audio instead of silently reusing stale speech.

## Export and pipeline stage semantics

The generation pipeline `export` stage is a durable readiness/checkpoint boundary. It does not by itself write user-requested export files. Concrete transcript, manifest, metadata, and audio files are produced by explicit CLI export or Episode Library export through `EpisodeLibraryExportService`.

This separation prevents tests or UI copy from confusing pipeline completion with artifact export. See `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md` for the stage-by-stage contract.

## Developer contracts

Implementation work should route surfaces through shared services instead of one-off UI or CLI shortcuts:

- `GenerationStartService` owns readiness checks and duplicate-safe generation start.
- `PreflightService` owns provider/model/TTS/FFmpeg readiness checks.
- `PipelineOrchestrator` owns durable stage transitions, checkpointing, pause, cancel, and resume.
- `EpisodePlannerService`, `HostTurnService`, `LLMHostTurnProvider`, `LLMDirectorDecisionProvider`, and `LLMTranscriptVerifier` own provider-backed text generation and validation boundaries.
- `TTSGenerationStage`, `TTSProviderRegistry`, and `TTSArtifactRepository` own provider-backed speech generation, cache reuse, status normalization, and per-turn audio artifacts.
- `EpisodeLibraryExportService` owns concrete export files.

When adding generation behavior, update both user and developer documentation, add tests for durable persisted state, and prove that deterministic behavior is available only through configured fake/development provider adapters.

## Persisted-data compatibility

Persisted user configuration is versioned and non-secret. Existing provider records with concrete adapter types should keep loading as optional fields are added; defaults such as timeout, response format, and empty voice catalogs must remain safe. Generic legacy provider types such as `llm` and `tts` are ambiguous and should fail with actionable guidance to select a concrete adapter.

Existing project databases should keep loading episodes, runs, transcripts, TTS artifacts, and audio timeline/export state across compatible schema evolution. When automatic migration is safe, normalize in repository boundaries. When it is unsafe, fail closed with a clear message rather than guessing provider, model, voice, or credential semantics.
