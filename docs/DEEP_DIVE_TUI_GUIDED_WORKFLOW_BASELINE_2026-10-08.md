# Deeper Dive Guided Workflow Baseline

**Captured:** 2026-10-08
**Baseline master:** 315f1d2f2ab43edc3929b59eaf1649fda10133f8
**Purpose:** Preserve the pre-guided-workflow Textual architecture and UX facts before replacement.

This document is evidence for GW-100. It is a historical baseline, not the desired end state. The guided workflow must preserve the listed production boundaries and advanced capabilities while replacing the normal subsystem-first path.

## Application shell and navigation

The pre-guided `DeeperDiveApp` owns one `ProductionComposition` and exposes two flat navigation groups:

- global: `home`, `providers`, `settings`, `help`;
- project: `sources`, `research`, `hosts`, `episode`, `generate`, `library`.

The shell binds Home/Providers/Settings/Help and the six project destinations directly. Normal users therefore see implementation subsystems as peer destinations rather than a task-oriented flow.

`HomeProjectsScreen` owns project create/open/rename/delete. Existing specialist screens remain separate: Sources, Research, Hosts, Episode Setup, Episode Plan, Preflight/Generate, Generation Monitor, Transcript Review, Providers, Settings, Help, and Library.

## Production boundaries that guided flows must reuse

`DeeperDiveApp` constructs or receives a `ProductionComposition`. That composition remains the production application context and owns or exposes:

- `DeeperDiveService` for project/source workflows and workspaces;
- `ProviderController`, provider factory, runtime registries, and reload publication;
- `PersistentResearchController`;
- `EpisodeConfigurationService`;
- `EpisodePlannerService` through composition planning factories;
- shared preflight and `GenerationStartService`;
- generation monitor/run-state services and `PipelineOrchestrator`;
- Transcript Review / targeted repair;
- TTS, audio, playback, library, and export boundaries.

Guided screens must call these boundaries instead of copying business behavior.

## First-run baseline

`first_run.py` currently provides a side-effect-free readiness probe only. It reports:

- FFmpeg availability;
- KittenTTS import availability;
- configured provider names;
- which configured providers appear local.

It does not store a setup-complete flag and does not currently provide the eight-step first-run wizard, role assignment, voice/default collection, or durable guided resume state. The new implementation should preserve the useful probe while deriving completion from current production/configuration readiness.

## Episode Setup baseline

The pre-guided `EpisodeSetupScreen` is deliberately implementation-facing. Its normal form exposes:

- episode title, focus, audience, technical depth, raw duration seconds, and style;
- **Host IDs in order, comma separated**;
- comma-separated must-cover and avoid-topic fields;
- raw research-policy and citation-behavior strings;
- direct Build Plan and Quick Deep Dive actions.

The screen persists through `EpisodeConfigurationService`, validates host IDs against the project repository, and routes planning through the configured production planning service. Those production boundaries are correct and must be reused; the raw-ID/string-heavy presentation is the UX being replaced for the normal path.

## Baseline acceptance implications

The guided remediation must therefore:

1. replace the default flat subsystem-first path with user-goal-first Home/New Deep Dive/Projects/Library navigation;
2. retain access to the advanced specialist screens;
3. replace raw host IDs and implementation strings in the normal episode flow with friendly selections;
4. keep production persistence, provider, planning, preflight, generation, repair, and export services authoritative;
5. compute wizard progress from durable production/configuration state rather than maintaining a second completion database.
