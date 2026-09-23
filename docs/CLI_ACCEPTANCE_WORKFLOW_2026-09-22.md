# CLI Acceptance Workflow Contract

**Created:** 2026-09-22  
**Related remediation items:** DDR-061, DDR-062, DDR-063, DDR-064, DDR-100, DDR-101, DDR-105, DDR-111, DDR-139, DDR-150

This document defines the deterministic CLI acceptance workflow that must be used for final remediation qualification. It is intentionally stricter than command-existence coverage: a command only counts as accepted when it routes through the shared production services and leaves durable, inspectable artifacts.

## Scope

The CLI workflow must exercise the same production composition path used by the TUI:

- provider construction through persisted provider configuration and `ProviderFactory`;
- episode planning through `EpisodePlannerService`;
- generation through `PipelineOrchestrator`;
- run control through durable generation-run state;
- export through the shared episode export path;
- visible errors through the canonical sanitizer.

A CLI-specific shortcut, metadata-only placeholder, or fixture-seeded result is not sufficient evidence for completion.

## Deterministic setup

Ordinary CI must not require paid credentials or live external services. The workflow should create a temporary data directory and persist fake providers through the same configuration file used by production startup:

```json
{
  "providers": {
    "planner": {"provider_type": "fake", "default_model": "fake-v1"},
    "speech": {"provider_type": "fake-tts"}
  },
  "defaults": {
    "episode_planning": "planner:fake-v1",
    "host_generation": "planner:fake-v1",
    "directing": "planner:fake-v1",
    "verification": "planner:fake-v1"
  }
}
```

The acceptance workflow may use deterministic fake providers, but only at the provider boundary. The command handlers themselves must use the same production-composed service graph used by non-test runs.

## Required command path

A complete CLI fake-provider acceptance run must perform these steps in order:

1. `project create` creates a real project record.
2. `source add` imports at least one local file or directory source.
3. `host create` or equivalent host configuration creates/selects hosts.
4. `host voice` assigns a configured TTS provider and voice.
5. `episode create` creates a durable episode configuration with concrete hosts, focus, duration, style, and research policy.
6. `episode plan` builds and persists a plan through the shared planner.
7. `episode generate` creates/selects a run and executes the shared pipeline to a documented terminal state.
8. `episode status` reports durable run state created by generation, not a hand-seeded fixture.
9. `episode export` writes transcript, manifest, metadata, and audio where present through the shared exporter.
10. `episode pause`, `episode resume`, and `episode cancel` are covered by a deterministic control matrix, either as part of the main workflow or a separate controlled-run test.

## Required assertions

The acceptance test must assert all of the following:

- generation does not stop at a newly-created `pending` run;
- the final successful generation path reaches `completed` or another explicitly documented terminal/control state;
- durable transcript turns exist for the selected episode;
- deterministic TTS/audio artifacts exist when the fake TTS path is configured;
- status reads the same run state that generation/control wrote;
- export writes actual files, not only a status label or JSON metadata placeholder;
- exported transcript content includes generated turn text from the selected episode;
- exported manifest records the selected project/source provenance;
- exported metadata contains the selected `project_id`, `episode_id`, `run_id`, title, and run state;
- exported audio, when present, is episode-specific and copied from the selected episode identity;
- JSON output remains machine-readable for create, plan, generate, status, and export commands;
- failure paths are sanitized before reaching stderr.

## State-control matrix

The CLI control tests should cover durable state transitions rather than command labels alone:

| Scenario | Required evidence |
| --- | --- |
| pending to running/completed | pipeline stages execute and durable completed units exist |
| running to paused | pause request reaches a safe boundary and persists `paused` |
| paused to resumed/completed | resume invokes the orchestrator from durable state |
| running to cancelled | cancel request reaches a safe boundary and persists `cancelled` |
| illegal transition | command returns non-zero with sanitized actionable text |
| process reconstruction | a new composition instance can read and continue eligible run state |

## Export contract

`episode export` must use the shared export implementation described in `docs/EXPORT_ARTIFACT_CONTRACT_2026-09-22.md`. A CLI export that writes only an episode-summary JSON file is not sufficient for DDR-063, DDR-101, DDR-111, or DDR-139.

The JSON output for a successful export should report concrete artifact paths. At minimum, consumers must be able to identify:

- transcript path;
- source/provenance manifest path;
- metadata path;
- audio path or explicit `null` when no audio is present;
- selected episode identity;
- selected run identity.

## Completion rule

This document is supporting qualification guidance. It does not mark DDR-111 or the related R7/R11/R14 items complete by itself. Completion requires the corresponding implementation and tests to be merged to `master`, exact-head CI to pass, the authoritative remediation TODO to be reconciled, and merged-master CI to pass.
