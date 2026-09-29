# Production generation architecture

This note documents the developer-facing contracts behind provider-backed production generation. It complements `docs/ARCHITECTURE.md`, `docs/GENERATION_PIPELINE_STAGE_SEMANTICS.md`, `docs/GENERATION_RUN_SELECTION_POLICY.md`, and the post-review remediation spec `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_SPEC_2026-09-27.md`.

## Explicit composition and generation-start boundary

`ProductionComposition` is the explicit typed owner of production provider runtime, generation services, and pipeline operations. It is injected into the TUI/controllers that require production behavior rather than discovered through hidden `DeeperDiveService` attributes. `DeeperDiveService` remains the workspace/repository facade.

`GenerationStartService` is the shared CLI/TUI readiness and run-selection boundary. Product surfaces call it before starting generation instead of implementing independent readiness/run-selection logic. It builds production preflight, blocks before run creation when appropriate, applies duplicate-safe run selection, and exposes the durable run used by monitor, CLI status/control, and Episode Library actions.

## Transactional provider runtime

Provider save/edit/remove builds and validates a complete candidate `ProviderBuildResult` before replacing durable configuration. Persistence occurs only after the candidate runtime builds successfully; runtime publication occurs only after persistence succeeds. Failed candidate changes preserve both the previous durable config and the previous live runtime. Successful same-session changes atomically refresh planning, directing, host generation, verification, TTS, repair, preflight, health, and discovery consumers.

One shared locality/network-scope policy classifies provider routes. Explicit `network_scope` overrides inferred adapter defaults, and CLI/TUI/preflight consume the same classification.

Credential values remain secret material. Provider configuration stores references such as environment-variable names, and status/diagnostics/metadata/logs/exports pass through the canonical sanitizer before durable or user-visible output.

## Production role preflight

Preflight derives the model roles that the selected episode will actually execute rather than validating a hard-coded subset. `episode_planning` is required when no valid usable plan exists, `host_generation` is required while conversation work remains, and configured directing/verification roles are included when production will call them. The resolver is extensible to future execution roles.

For each executed role, preflight and production share provider existence, model availability, provider health, voice availability, and network/local-only policy. Once a durable run exists, execution-time assignment/configuration/provider failures are caught inside the durable execution boundary and persist failed state, stage, stable code, sanitized message, and timestamp rather than leaving stale pending/running state.

## Plan validity and evidence integrity

A generation-usable plan must belong to the selected episode, contain at least one parseable coherent segment, use non-empty titles and positive durations, reference participating lead hosts, keep evidence within project/episode scope, and have a status allowed for generation. Planning skips only a valid usable plan; empty, corrupt, semantically invalid, or disallowed plans trigger planning instead.

Evidence validation uses an explicit active/disabled distinction. An active empty scope means no evidence IDs are valid; it does not disable validation. `EpisodePlannerService` edit/regeneration rejects nonexistent and cross-project evidence while preserving valid in-scope evidence.

## Multi-turn conversation generation

The public conversation-generation service loads the ordered durable plan and `ConversationState`, then repeatedly generates the next bounded unit until the episode completes. Each turn persists text, evidence, provider/model identity, state, and checkpoint atomically. The existence of one prior turn is not stage completion.

Director signals are durable control inputs: `CONTINUE` remains in the current segment, `COMPLETE_SEGMENT` advances, and `COMPLETE_EPISODE` terminates cleanly. A deterministic bounded fallback applies when directing is intentionally unassigned. Maximum turns per segment/episode plus target word/duration budgeting prevent infinite loops. Resume starts from the first incomplete durable unit and does not duplicate already committed turns.

## Evidence and generated provenance

Provider-backed directing and host-turn generation receive an explicit evidence scope derived from the durable plan and indexed source chunks. Provider-returned citations outside that scope are rejected. Valid evidence IDs are persisted on transcript turns and resolved to source passages during review/export. Multi-episode acceptance proves turn, evidence, timeline, playback, and export identity remain episode-scoped inside one project.

## TTS, composition, and artifact identity

Production composition is WAV-only. Preflight rejects non-WAV selected TTS response formats before expensive synthesis, including OpenAI-compatible configurations that request MP3. KittenTTS remains WAV-only.

Successful TTS validates returned provider, voice, explicitly requested model when applicable, format/path-extension consistency, and non-empty audio before saving success. `tts_artifacts` is a per-turn artifact-reference table: turns may share cache key/artifact/path when synthesis inputs are identical, but each turn has a durable reference row. Cache identity includes text, provider, voice, model, response format, and synthesis settings.

Production audio normalization uses FFmpeg/libswresample and preserves the canonical 24 kHz mono signed-16-bit WAV contract. Cross-module callers use the public FFmpeg conversion/transcode API rather than private composer methods.

Transcript repair performs real claim extraction/reverification and summary/context update, invalidates affected TTS/timeline/final audio, and invokes public `ProductionComposition.regenerate_episode_audio()` for regeneration. Cache cleanup is reference-aware: shared live physical artifacts are retained, while obsolete unreferenced files are collected so repeated repair does not create unbounded orphans.

## Canonical sanitizer boundary

One recursive sanitizer protects persisted pipeline failures, diagnostics/structured logs, CLI/TUI errors and status, provider health/model/voice messages, export metadata, and diagnostic bundles. It recognizes authorization/API-key/token/access-token/refresh-token/secret/client-secret/password/cookie variants plus Bearer strings, assignments, quoted maps, credential URLs, nested collections, and exception cause/context chains. Export metadata sanitizes recursively immediately before serialization.

## Stage and export semantics

`PipelineOrchestrator` owns durable stage transitions, completed-unit checkpoints, pause/cancel boundaries, retry behavior, and failure state. Some stages are intentional durable readiness/checkpoint boundaries rather than file-writing stages. The pipeline `export` stage means generation is ready for explicit export; CLI export and Episode Library export create concrete transcript, manifest, metadata, and audio files.

Episode exports include episode/run identity and reserve episode-specific filenames. Transcript Review playback resolves audio and timeline by the currently selected episode. Multi-episode acceptance verifies no turn/evidence/TTS/timeline/playback/review/library-export crossover.

## TTS artifact status and persisted compatibility

The canonical successful TTS artifact status is `complete`. The legacy success value `completed` remains readable and is normalized by `TTSArtifactRepository`; new writes use `complete` only. Current provider config, existing projects/episodes/runs/turns/provider-identity rows, audio timelines, and exports remain readable through current repositories/services unless an explicit tested migration is introduced.

Compatibility tests should create or emulate representative older persisted rows and load them through current repositories/services rather than relying only on fixture JSON comparisons. Any future migration must be idempotent and failure-safe.

## Deterministic acceptance fixture

The shared acceptance fixture family configures fake LLM/TTS providers through `UserConfigStore`/`ProviderFactory`, creates project/corpus/hosts/episode through public application services, builds plans through `EpisodePlannerService`, executes the shared generation pipeline, and produces multiple turns, TTS artifacts, timeline/final audio, and exports. Normal acceptance does not seed approved plans directly through repository writes.

The fixture family is reused for CLI generation/status/export and auto-planning, TUI provider save/reload/preflight/generate/monitor/review/library/export, duplicate start/pause/resume/cancel, evidence/provenance, TTS artifact identity, and two-episode isolation. Direct database/repository seeding remains appropriate only for explicit compatibility/migration tests.

## CI and Kitten qualification policy

Mandatory deterministic quality gates do not require paid credentials, cloud-provider availability, or a GPU. They exercise production boundaries with configured fake/local providers.

The mandatory fresh-machine job additionally performs a bounded real KittenTTS Micro CPU smoke. This gate is **external-network dependent**: it installs KittenTTS from its external source and may download runtime/model assets. This is an intentional mandatory qualification policy, not an offline deterministic test. Network availability can therefore affect that job. CI documentation must not claim that mandatory CI has no external dependency.

Fresh-machine qualification builds a wheel from the exact checked-out head, installs it into a clean virtual environment, rejects source-tree imports, launches installed CLI and TUI entry points, exercises installed project/source/host/episode/planning/generation/export behavior, validates generated transcript/manifest/metadata/audio and sanitizer behavior, and runs the real Kitten CPU smoke.

## Required quality gates

Final qualification includes dependency-lock validation, Ruff format/lint, mypy, full pytest, package build, CLI/import smoke, multi-turn generation, provider transaction/runtime, preflight/role, plan/evidence, security/redaction, TTS format/identity/cache, transcript repair, CLI/TUI acceptance, multi-episode isolation, installed-wheel fresh-machine acceptance, and the mandatory real-Kitten qualification gate.
