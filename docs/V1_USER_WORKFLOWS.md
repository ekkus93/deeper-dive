# V1 user workflows

This guide records the production V1 workflow and the behavior shared by the Textual TUI and CLI. The production-generation follow-up is tracked in `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_TODO_2026-09-25.md` and the companion spec `docs/DEEP_DIVE_PRODUCTION_GENERATION_FOLLOWUP_SPEC_2026-09-25.md`.

## Providers and defaults

Provider configuration persists a concrete adapter identity rather than only a capability class. Supported production routes include OpenAI-style LLMs, Ollama, llama-server/OpenAI-compatible local LLMs, KittenTTS, OpenAI/OpenAI-compatible TTS, and ElevenLabs-style TTS. Provider health, model discovery, and voice discovery use the configured adapter through the production provider factory. Unsupported capabilities are reported separately from unhealthy or misconfigured providers.

Same-session provider edits are expected to refresh every production runtime consumer in the current process. After a provider is saved, removed, or reloaded through the TUI/controller, preflight, planning, conversation generation, TTS generation, provider health, and export/composition must see the same runtime provider registries without requiring an app restart. Provider credentials remain non-persistent secrets and must not appear in TUI status, CLI output, diagnostics, logs, metadata, or exports.

Effective model-role configuration is resolved in this order: episode overrides, then project defaults, then user defaults, followed only by documented built-in fallbacks. Preflight and generation consume the same resolved assignments. Production auto-planning uses the configured `episode_planning` role rather than a first-provider fallback; missing, unknown, unavailable, unhealthy, or invalid planning providers fail before conversation, TTS, or composition begins. CLI `episode generate`, TUI Generate, and monitor/background generation surface those failures through sanitized actionable messages.

## Research

Research analysis operates on the project corpus and persists research gaps with provenance. Selected or all eligible gaps can then be researched through the shared research controller. Accepted supplemental material remains distinguishable from user sources. Persisted network/research policy controls automated research; ordinary CI uses deterministic search/fetch doubles and does not make live web requests.

## Normal TUI episode workflow

Create or select a project, add sources, configure hosts, then create/configure an episode. Build Plan persists a plan through the shared planning service. Preflight validates sources, hosts, duration, provider/model routing, voices, and FFmpeg/readiness. Generate creates/selects a durable generation run and executes the shared pipeline. The Generation Monitor reflects durable progress and supports checkpoint-safe pause, resume, and cancel. Transcript Review supports claims/citations, targeted repair, episode-specific playback, and review export. Episode Library export writes episode-specific transcript, source/provenance manifest, metadata, and audio when present.

Provider-backed generation carries source/plan evidence IDs into directing and host-turn generation. Generated citations are constrained to indexed source chunks in the current project/episode scope, persisted on transcript turns, and resolved to source passages during export. Provider-returned evidence outside the supplied scope is rejected rather than silently accepted.

TTS synthesis honors the configured provider response format and records the actual provider/voice/model/format identity on each turn artifact. OpenAI-compatible TTS providers may use configured non-default formats such as `mp3`; WAV-only providers, including KittenTTS Micro, reject unsupported response formats before claiming success. Duplicate text/voice/model/settings may reuse one cached physical artifact, but every generated turn still has its own durable artifact-reference row. Transcript repair invalidates stale audio when text, provider, voice, model, response format, or synthesis settings change.

Episode audio composition currently supports validated WAV turn artifacts. The composed episode WAV has one coherent header and combined PCM frames in turn order. Missing, empty, unreadable, unsupported, compressed/container, or mismatched TTS artifacts fail with sanitized diagnostics before composition is marked complete; they are not byte-concatenated into an invalid output file.

## Quick Deep Dive

Quick Deep Dive is a convenience entry point into the same durable episode workflow. User defaults and project overrides take precedence over built-ins. Built-in fallback behavior uses the Curious Explainer and Skeptic hosts, an approximately 20-minute target, and the Useful research policy. The resulting episode is normally planned, preflighted, generated, reviewable, resumable, and exportable; it is not a separate placeholder pipeline.

## CLI generation and control

The episode CLI uses the same production composition and durable services as the TUI. `episode plan` persists a shared plan. `episode generate` executes generation rather than merely creating a pending run. `episode pause` reaches a safe durable pause boundary, `episode resume` continues from a valid checkpoint, and `episode cancel` reaches the documented cancelled state. Illegal state transitions fail explicitly. `episode status` reports durable run state and `episode show-plan` reads the persisted plan.

`episode export` uses the shared export path and writes transcript, source/provenance manifest, metadata, and audio when available. Artifact names and metadata retain selected episode/run identity so multiple episodes in one project do not cross-contaminate output.

## KittenTTS benchmark

The Kitten benchmark performs actual timed synthesis through the shared benchmark service. Output includes synthesis elapsed time, output-audio duration, real-time factor or equivalent throughput, and model/runtime/voice context. Kitten install and status commands remain separate. The fresh-machine qualification keeps real KittenTTS CPU synthesis as a bounded smoke test rather than a normal unit-test dependency. KittenTTS Micro is treated as WAV-only in production generation; users should choose a WAV response format for Kitten-backed hosts.

## Privacy and error redaction

User-visible provider and pipeline failures pass through the canonical sanitizer before persistence or presentation. It redacts authorization credentials, API-key/token/environment-style assignments, credentials embedded in URLs, and representative provider SDK exception forms while preserving useful non-secret context. The same boundary is used for persisted pipeline failures, diagnostic bundles, structured logs, CLI errors, and TUI-visible errors. Normal diagnostics and exports must not contain stored credentials.
