# Post-review final reconciliation evidence — 2026-09-29

This document records exact current-master evidence for reconciling `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md`. It is evidence, not a competing checklist.

## Exact qualified heads

- Implementation/documentation head: `d1f640b01002e186fdb6e85d28a1c9840a5bd75f`
- CI run: `36576824294`, result `success`.
- Evidence-consolidation head: `2b3ad696d4896bad755d154850e08b48a7fa99d2`
- CI run: `36579387382`, result `success`.
- Both `quality` and `fresh-machine` jobs passed on the evidence-consolidation head.

## R9 — shared acceptance fixture

The reusable fixture family creates provider configuration, project/source corpus, hosts, episode configuration, plan, generation runs, evidence-bearing transcript turns, TTS artifacts, timeline/audio, and exports through production boundaries. It is reused for CLI generation/status/export, TUI preflight/generation/monitor/review/library/export, controls, auto-planning, and multi-episode isolation.

The installed-wheel gate deliberately reconstructs the same public production workflow from the installed package rather than importing a repository test helper. That is a stronger isolation boundary for PRR-181's installed-wheel requirement. Redundant end-to-end setup has been consolidated into the fixture family; focused unit, compatibility, and boundary tests remain separate because they provide independent coverage rather than redundant setup.

## R10 — CI/fresh-machine policy

The selected Kitten policy is mandatory real-Kitten qualification in the fresh-machine job. `docs/PRODUCTION_GENERATION.md` explicitly documents that this gate is external-network dependent because it installs the real KittenTTS runtime and downloads runtime/model assets. Mandatory deterministic coverage remains on fake/local providers and requires no paid credentials or paid cloud calls.

CI runs `36576824294` and `36579387382` prove the mandatory fresh-machine job executed successfully. The gate includes these named operations:

1. `Build and install wheel in clean environment`
2. `Launch installed CLI and TUI entry points`
3. `Exercise installed-wheel corpus and episode workflow`
4. `Install real KittenTTS runtime`
5. `Real KittenTTS Micro CPU smoke`

The installed-wheel workflow exercises project/source/host/episode setup, planning/auto-planning, generation, export, non-empty transcript/manifest/metadata/audio, and sanitizer behavior through installed code. This satisfies PRR-190, PRR-191, PRR-211 installed-wheel qualification, and PRR-211 chosen real-Kitten qualification.

## R11 — documentation and compatibility

`docs/PRODUCTION_GENERATION.md` documents all PRR-200 subjects: multi-turn/multi-segment generation, completion/safety bounds, transactional provider save/remove rollback, exact role preflight, valid-plan policy, plan evidence edit/regeneration validation, TTS/composition format policy, canonical redaction/export guarantees, repair reverification/audio regeneration, reference-aware cache cleanup, explicit composition ownership, and Kitten qualification policy.

`tests/test_post_review_compatibility.py::test_persisted_state_reopens` creates production state through the shared acceptance fixture, completes generation/export, rebuilds a fresh `ProductionComposition`, and proves current provider config, episode/run state, turns plus provider-identity rows, timeline, transcript, manifest, metadata, and audio remain readable. Existing TTS compatibility tests prove legacy `completed` TTS rows normalize to canonical `complete`. No schema migration is required by this remediation, so migration-specific idempotence/failure-safety requirements are not applicable.

## R12 — focused qualification

`tests/test_pipeline.py` provides focused durable control evidence:

- `test_failed_run_can_resume_from_completed_stage_checkpoints`
- `test_pause_requested_before_stage_stops_without_losing_prior_units`
- `test_pause_during_uninterruptible_stage_finishes_stage_then_pauses`
- `test_resume_after_restart_continues_from_durable_stage_boundaries`
- `test_cancel_during_tts_preserves_completed_units_and_stops_downstream`
- `test_cancelled_runs_cannot_resume`

The shared acceptance fixture additionally covers duplicate start, pause/resume, and cancel through production composition. Therefore PRR-211 pause/resume/cancel/resume-after-failure has focused regression evidence.

The exact-head CI quality job covers lock validation, Ruff format, Ruff lint, mypy, pytest, package build, and CLI/import smoke. The fresh-machine job covers the installed-wheel and selected real-Kitten qualification gates.

## R13 — implementation-evidence reconciliation

Implementation SHAs, policy-required PR numbers, focused tests by cluster, and exact-head CI evidence are recorded in the canonical TODO closeout section and this evidence document. The implementation is production-wired rather than fixture-only: the fixture and installed-wheel tests enter through the same public production services used by CLI/TUI surfaces. The companion post-review spec findings are represented by PRR-100 through PRR-211 and have implementation plus qualification evidence.

At `2b3ad696d4896bad755d154850e08b48a7fa99d2`, all substantive unchecked requirements remaining in the canonical TODO have evidence sufficient for reconciliation: PRR-181 installed-wheel/redundant setup, PRR-190, PRR-191, PRR-200, PRR-201, and PRR-211 controls/installed-wheel/Kitten. PRR-220 evidence-recording requirements are also satisfied by the canonical closeout section plus this document. PRR-221 remains a closeout sequencing gate: reconcile the canonical TODO on `master`, run exact-head CI on that reconciliation commit, reload TODO/spec, verify zero unchecked requirements, and only then declare remediation complete.

## Final qualification rule

Do not declare completion merely from an earlier implementation head. The canonical TODO reconciliation commit itself must receive exact-head CI. After that run passes `quality` and `fresh-machine` (including real Kitten), reload the TODO and companion spec from that exact head and record the final SHA/run as closeout evidence.
