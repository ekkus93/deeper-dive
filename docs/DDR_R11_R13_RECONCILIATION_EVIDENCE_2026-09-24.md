# DDR R11-R13 Reconciliation Evidence — 2026-09-24

This document batches the merged evidence for remediation items that are implemented and qualified but were still unchecked in `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md` on `master` after PR #377.

## Scope

- R11: DDR-100 through DDR-107.
- R12: DDR-111 and DDR-112.
- R13: DDR-120 through DDR-122.

DDR-110 remains intentionally outside this reconciliation scope because the installed-wheel/fresh-machine workflow still needs the stronger preflight and secret-redaction probe before its checkbox set should close.

## R11 evidence

### DDR-100 — Replace weak Generate assertions

Evidence now covers real generation execution rather than pending-run creation:

- `tests/test_preflight_generate_integration.py::test_generate_starts_real_pipeline_and_reuses_active_run` verifies the Generate action reuses the selected run, starts the real generation controller, executes all `DEFAULT_STAGES`, and reaches `completed` rather than stopping at `pending`.
- `tests/test_ddr061_cli_generate.py::test_cli_generate_reaches_completed_state_and_persists_episode_artifacts` verifies CLI generation reaches `completed`, persists deterministic transcript turns, persists completed TTS artifacts, and writes episode audio.
- `tests/test_pipeline.py`, `tests/test_pipeline_failure_redaction.py`, `tests/test_generation_monitor_production.py`, and `tests/test_error_redaction_surfaces.py` cover failed terminal state and actionable sanitized error surfacing.
- Current merged-master CI passed on `12c04a436de96ca1160b1a3e35451f0a5d1f2e95`: run `35969893747`.

### DDR-101 — Replace weak Export assertions

Evidence now covers real exported files, episode identity, and metadata/provenance content:

- `tests/test_ddr031_export_qualification.py::test_episode_library_export_writes_complete_episode_specific_artifact_set` verifies transcript, manifest, metadata, and audio files in the selected output directory, episode-specific filenames, deterministic transcript content, source/provenance manifest content, and metadata run/episode identity.
- `tests/test_ddr063_cli_export.py::test_cli_episode_export_uses_shared_artifact_exporter` verifies CLI export uses the shared exporter and returns concrete transcript, manifest, metadata, and audio files containing the completed episode/run identity.
- `tests/test_episode_library_export_integration.py` and `tests/test_ddr041_production_pipeline_artifacts.py` verify Episode Library and Quick Deep Dive export paths produce real artifacts rather than status labels.
- Current merged-master CI passed on `12c04a436de96ca1160b1a3e35451f0a5d1f2e95`: run `35969893747`.

### DDR-102 — Transcript Review direct tests

- PR #373 merged as `333357e4e10f2610b446616e77fc9e1d54cd0c06` and added `tests/test_ddr102_transcript_review_direct.py`, covering chapter/turn rendering, claims, citation rendering, source-passage presentation, and selected-episode transcript-review export.
- PR #373 exact-head CI passed: run `35953375821`; merged-master CI passed: run `35953480035`.
- Existing `tests/test_transcript_review_screen.py` covers production-composed targeted turn repair, section repair, missing-provider actionable failure, regenerated TTS/audio artifacts, refreshed timelines, and selected-episode audio identity.
- Existing PR #347 (`a0abdeb0e1356a9e2a4a8a84c46aa092469344ef`) covered production-wired `TargetedRepairService`; exact merged-master CI passed: run `35881322893`.

### DDR-103 — Production-composition integration suite

- PR #372 merged as `877d69b23802ac56c14ab25808de30da28f29077` and added `tests/test_ddr103_production_composition_acceptance.py`.
- Coverage includes durable fake-provider configuration, provider-factory registration, local source corpus import, host/episode configuration, shared planning, preflight, production generation, transcript review, review export, and episode export through normal production composition.
- Deterministic adapters are substituted only at provider boundaries while the test uses `ProductionComposition.build()`, shared services, and production artifact contracts.
- PR #372 exact-head CI passed: run `35950840851`; merged-master CI passed: run `35950936057`.

### DDR-104 — Multi-episode isolation matrix

- PR #367 merged as `47ba4abcac55a00283c5708d81dcbe7de604746a` and added `tests/test_ddr104_multi_episode_isolation.py`, covering distinct completed run identities, transcript turns, playback/audio paths, transcript-review exports, shared-export artifacts, metadata, and deterministic audio output for two episodes in one project.
- PR #367 exact-head CI passed: run `35937739216`; merged-master CI passed: run `35938036925`.
- PR #368 merged as `3119e2032cfa7f408f6fdf5cd9f6d0c793fc825c` and added `tests/test_ddr104_episode_mutation_isolation.py`, covering duplicate/delete isolation and non-contamination of sibling/duplicate episode records and generation-run state.
- PR #368 exact-head CI passed: run `35943772573`; merged-master CI passed: run `35943909393`.

### DDR-105 — Run-state/control matrix

- PR #369 merged as `cc81bcb18a545410a44fe3ee46fdc585394e7a04` and added `tests/test_ddr105_run_state_matrix.py`.
- Coverage includes pending to running, running to failed, running to completed, safe-boundary pause, paused to resumed execution after orchestrator reconstruction, durable checkpoint reuse, and illegal terminal resume rejection.
- Existing `tests/test_pipeline_control_transitions.py`, `tests/test_ddr062_cli_control.py`, and `tests/test_generation_monitor_production.py` cover cancellation and CLI/TUI control surfaces through the shared production run-state/control layer.
- PR #369 exact-head CI passed: run `35947104335`; merged-master CI passed: run `35947205755`.

### DDR-106 — Provider-routing matrix

- PR #370 merged as `78d59078d34100a58104942976e1d9cf03d0152f` and added `tests/test_ddr106_provider_routing_matrix.py`.
- Coverage includes OpenAI LLM, Ollama, llama-server/OpenAI-compatible local inference, KittenTTS, OpenAI TTS, OpenAI-compatible TTS, ElevenLabs, local/remote network-scope classification, missing credentials, and unsupported provider types without live network calls or paid credentials.
- Existing provider-specific tests continue to exercise adapter normalization and error handling: `tests/test_openai_llm.py`, `tests/test_ollama_llm.py`, `tests/test_llama_server_llm.py`, `tests/test_openai_tts.py`, `tests/test_openai_compatible_tts.py`, `tests/test_elevenlabs_tts.py`, and `tests/test_kitten_tts.py`.
- PR #370 exact-head CI passed: run `35947509340`; merged-master CI passed: run `35947627143`.

### DDR-107 — Security regression matrix

- PR #371 merged as `cca0f028917e3bdc90f016b7a932f0ddcdf81fb5` and added `tests/test_ddr107_security_regression_matrix.py`.
- Coverage includes authorization-header, API-key, token, environment-style secret, credential-bearing URL, persistence, diagnostic bundle, structured-log, CLI-visible, and TUI-visible redaction cases.
- Existing tests continue to cover canonical sanitizer behavior across logs, diagnostics, provider errors, persistence, and user-visible surfaces: `tests/test_diagnostics.py`, `tests/test_diagnostics_secret_matrix.py`, `tests/test_diagnostics_secret_redaction.py`, `tests/test_privacy_security_matrix.py`, and `tests/test_user_error_redaction.py`.
- PR #371 exact-head CI passed: run `35950250528`; merged-master CI passed: run `35950387008`.

## R12 evidence

### DDR-111 — CLI fake-provider acceptance workflow

- PR #376 merged as `676edd9a198c958e978e25185f2f938e0ea6afc4` and added `tests/test_ddr111_cli_acceptance.py`.
- Coverage includes project creation, local corpus import, host/episode creation, shared planning, actual generation to `completed`, status verification, real artifact export/content validation, and durable pause/resume through the CLI control path.
- PR #376 exact-head CI passed: run `35968887942`; merged-master CI passed: run `35969024940`.

### DDR-112 — TUI deterministic acceptance workflow

- PR #377 merged as `12c04a436de96ca1160b1a3e35451f0a5d1f2e95` and added `tests/test_ddr112_tui_acceptance.py`.
- Coverage includes production TUI service startup, deterministic provider configuration, project selection, Quick Deep Dive episode/plan creation, preflight, Generate click, monitor navigation/progression, production pipeline completion, transcript review content, Episode Library navigation, and real artifact export assertions.
- PR #377 exact-head CI passed: run `35969691078`; merged-master CI passed: run `35969893747`.

## R13 evidence

### DDR-120 — User documentation

- PR #374 merged as `d10a37d16ab46cf87357b2659ec0e15be0f9dd5a` and added `docs/V1_USER_WORKFLOWS.md`.
- Coverage includes concrete provider routes, configuration precedence, research, normal TUI generation, Quick Deep Dive behavior, CLI generation/control/export semantics, KittenTTS benchmarking, and privacy/error-redaction behavior.
- PR #374 exact-head CI passed: run `35956520535`; merged-master CI passed: run `35956659959`.

### DDR-121 — Developer architecture documentation

- PR #374 merged as `d10a37d16ab46cf87357b2659ec0e15be0f9dd5a` and added `docs/V1_ARCHITECTURE_CONTRACT.md`.
- Coverage includes the production composition root, provider factory, shared TUI/CLI service boundaries, durable run/control lifecycle, episode-specific artifact identity/export contract, sanitizer boundary, and deterministic CI provider strategy.
- PR #374 exact-head CI passed: run `35956520535`; merged-master CI passed: run `35956659959`.

### DDR-122 — Persisted-data compatibility

- PR #375 merged as `480261f24fa62b129db8026c9c0acccd5f4c7eb8` and added `tests/test_ddr122_persisted_compatibility.py`.
- Coverage includes reopening persisted projects and episodes after service reconstruction, loading existing concrete provider configuration records and rebuilding production adapters, no-op migration for concrete schema-v1 provider records, and actionable rejection of ambiguous legacy `llm`/`tts` provider identities.
- PR #375 exact-head CI passed: run `35961359719`; merged-master CI passed: run `35961473244`.

## Reconciliation status

The matching TODO checkboxes can be safely flipped for DDR-100 through DDR-107, DDR-111, DDR-112, and DDR-120 through DDR-122 once this evidence branch is exact-head qualified. DDR-110 remains open and should be the next R12 implementation target before R12 is considered complete.
