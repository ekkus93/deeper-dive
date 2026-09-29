# V1 user workflows

This guide records the production V1 workflow and the behavior shared by the Textual TUI and CLI. The current post-review remediation is tracked in `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md` and its companion spec.

## Providers and defaults

Provider configuration persists a concrete adapter identity rather than only a capability class. Supported production routes include OpenAI-style LLMs, Ollama, llama-server/OpenAI-compatible local LLMs, KittenTTS, OpenAI/OpenAI-compatible TTS, and ElevenLabs-style TTS. Provider health, model discovery, and voice discovery use the configured adapter through the production provider factory. Unsupported capabilities are reported separately from unhealthy or misconfigured providers.

Provider save/edit/remove is transactional: Deeper Dive validates and builds the complete candidate runtime before durable config is replaced, then publishes that runtime only after persistence succeeds. A failed provider change therefore leaves the previous durable config and live runtime usable. Same-session successful changes refresh planning, directing, host generation, verification, TTS, repair, preflight, and health consumers without requiring an app restart. Provider credentials remain non-persistent secrets and must not appear in TUI status, CLI output, diagnostics, logs, metadata, or exports.

Effective model-role configuration is resolved in this order: episode overrides, then project defaults, then user defaults, followed only by documented built-in fallbacks. Preflight derives the roles that the selected episode will actually execute. A missing valid plan requires `episode_planning`; remaining conversation work requires `host_generation`; configured directing and verification roles are validated when production will execute them. Provider existence, model availability, health, voice availability, and local/remote policy are shared between CLI and TUI preflight.

## Research

Research analysis operates on the project corpus and persists research gaps with provenance. Selected or all eligible gaps can then be researched through the shared research controller. Accepted supplemental material remains distinguishable from user sources. Persisted network/research policy controls automated research; ordinary CI uses deterministic search/fetch doubles and does not make live web requests.

## Normal TUI episode workflow

Create or select a project, add sources, configure hosts, then create/configure an episode. Build Plan persists a plan through `EpisodePlannerService`. A generation-usable plan belongs to the episode, contains at least one coherent segment with non-empty title and positive duration, references participating lead hosts, carries only in-scope evidence, and is in an allowed status. Empty, corrupt, invalid, or disallowed plans do not suppress auto-planning. Plan edit and regeneration validate evidence IDs; an active empty evidence scope rejects all evidence rather than disabling validation.

Preflight validates sources, hosts, duration, provider/model routing, voices, network policy, and FFmpeg/readiness. Generate creates/selects a durable generation run and executes the shared pipeline. Production conversation generation walks the ordered durable plan and emits successive turns rather than treating the first turn as completion. Director signals `CONTINUE`, `COMPLETE_SEGMENT`, and `COMPLETE_EPISODE` drive durable progress. Per-segment/per-episode turn bounds and target word/duration budgeting prevent a non-completing provider from running indefinitely. Interrupted work resumes from the first incomplete durable unit without duplicating previously committed turns.

The Generation Monitor reflects durable progress and supports checkpoint-safe pause, resume, and cancel. Transcript Review supports claims/citations, targeted repair, episode-specific playback, and review export. Repair clears stale claim/verification state for changed text, performs production reverification, refreshes conversation summary/context, invalidates affected audio, and regenerates TTS/timeline/final audio through the public production composition boundary. Unaffected turns remain intact.

Episode Library export writes episode-specific transcript, source/provenance manifest, metadata, and audio when present. Multiple episodes in one project retain independent turn, evidence, TTS, timeline, playback, review/export, filename, and run/episode metadata identity.

Provider-backed generation carries source/plan evidence IDs into directing and host-turn generation. Generated citations are constrained to indexed source chunks in the current project/episode scope, persisted on transcript turns, and resolved to source passages during export. Provider-returned evidence outside the supplied scope is rejected rather than silently accepted.

## TTS, composition, and cache behavior

Production composition is WAV-only. Preflight rejects a selected non-WAV TTS response format before expensive synthesis starts, so a configuration guaranteed to fail composition is not reported Ready. KittenTTS remains WAV-only. Successful TTS validates the returned provider, voice, explicitly requested model when applicable, response format/path extension, and non-empty audio before persisting success.

Production normalization uses FFmpeg/libswresample and writes the canonical 24 kHz mono signed-16-bit WAV contract. Duplicate text/voice/model/settings may reuse one cached physical artifact, but every generated turn still has its own durable artifact-reference row. Transcript repair invalidates stale audio when synthesis identity changes. Reference-aware cleanup preserves a physical cache file while another live turn still references it and removes obsolete unreferenced artifacts rather than allowing repeated repair to accumulate orphan files.

## Quick Deep Dive

Quick Deep Dive is a convenience entry point into the same durable episode workflow. User defaults and project overrides take precedence over built-ins. Built-in fallback behavior uses the Curious Explainer and Skeptic hosts, an approximately 20-minute target, and the Useful research policy. The resulting episode is normally planned, preflighted, generated, reviewable, resumable, and exportable; it is not a separate placeholder pipeline.

## CLI generation and control

The episode CLI uses the same explicit `ProductionComposition` and durable services as the TUI. `episode plan` persists a shared plan. `episode generate` auto-plans through the configured `episode_planning` provider when no valid persisted plan exists and then executes generation. `episode pause` reaches a safe durable pause boundary, `episode resume` continues from a valid checkpoint, and `episode cancel` reaches the documented cancelled state. Illegal state transitions fail explicitly. `episode status` reports durable run state and `episode show-plan` reads the persisted plan.

`episode export` uses the shared export path and writes transcript, source/provenance manifest, metadata, and audio when available. Artifact names and metadata retain selected episode/run identity so multiple episodes in one project do not cross-contaminate output.

## KittenTTS benchmark and qualification

The Kitten benchmark performs actual timed synthesis through the shared benchmark service. Output includes synthesis elapsed time, output-audio duration, real-time factor or equivalent throughput, and model/runtime/voice context. Kitten install and status commands remain separate.

Mandatory CI includes a bounded real KittenTTS Micro CPU smoke in the fresh-machine job. That qualification is intentionally **external-network dependent**: it installs KittenTTS from its external source and may download runtime/model assets. It does not use paid credentials or cloud-provider calls. The rest of the mandatory generation acceptance uses configured deterministic fake/local providers through the same provider factory and runtime boundaries. A network outage can therefore fail the mandatory Kitten qualification even when deterministic application tests pass; CI must not be described as fully offline.

## Privacy and error redaction

One canonical recursive sanitizer protects durable and user-visible output. It covers authorization/API-key variants, tokens including access/refresh tokens, client secrets, passwords, cookies, Bearer values, assignment-style secrets, quoted mappings, credentials embedded in URLs, nested collections, and exception cause/context chains while preserving useful non-secret context. The same boundary is used for persisted pipeline failures, provider health/discovery/status messages, diagnostic bundles, structured logs, CLI/TUI-visible errors, and export metadata. Provider configuration stores credential references rather than credential values.
