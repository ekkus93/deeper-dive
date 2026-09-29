# Post-review final reconciliation evidence — 2026-09-29

This document records exact current-master evidence for reconciling `docs/DEEP_DIVE_PRODUCTION_GENERATION_POST_REVIEW_REMEDIATION_TODO_2026-09-27.md`. It is evidence, not a competing checklist.

## Exact qualified head

- Qualified `master`: `d1f640b01002e186fdb6e85d28a1c9840a5bd75f`
- GitHub Actions CI run: `36576824294`
- Result: `success`
- `quality` job: success, including dependency-lock validation, Ruff format, Ruff lint, mypy, pytest, package build, and CLI/import smoke.
- `fresh-machine` job: success.

## R10 — CI/fresh-machine policy

The selected Kitten policy is mandatory real-Kitten qualification in the fresh-machine job. `docs/PRODUCTION_GENERATION.md` explicitly documents that this gate is external-network dependent because it installs the real KittenTTS runtime and downloads runtime/model assets. Mandatory deterministic coverage remains on fake/local providers and requires no paid credentials or paid cloud calls.

CI run `36576824294` proves the mandatory fresh-machine job executed these named steps successfully:

1. `Build and install wheel in clean environment`
2. `Launch installed CLI and TUI entry points`
3. `Exercise installed-wheel corpus and episode workflow`
4. `Install real KittenTTS runtime`
5. `Real KittenTTS Micro CPU smoke`

The installed-wheel workflow exercises project/source/host/episode setup, planning/auto-planning, generation, export, non-empty generated artifacts, and sanitizer behavior through installed code. This is sufficient evidence for PRR-190, PRR-191, PRR-211 installed-wheel qualification, and PRR-211 chosen real-Kitten qualification.

## R11 — Documentation and compatibility

`docs/PRODUCTION_GENERATION.md` now documents all PRR-200 subjects: multi-turn/multi-segment generation, completion/safety bounds, transactional provider save/remove rollback, exact role preflight, valid-plan policy, plan evidence edit/regeneration validation, TTS/composition format policy, canonical redaction/export guarantees, repair reverification/audio regeneration, reference-aware cache cleanup, explicit composition ownership, and Kitten qualification policy.

`tests/test_post_review_compatibility.py::test_persisted_state_reopens` creates production state through the shared acceptance fixture, completes generation/export, rebuilds a fresh `ProductionComposition`, and proves current provider config, episode/run state, turns plus provider-identity rows, timeline, transcript, manifest, metadata, and audio remain readable. Existing TTS compatibility tests prove legacy `completed` TTS rows normalize to canonical `complete`. No schema migration is required by this remediation, so migration-specific idempotence/failure-safety requirements are not applicable.

## R12 — control matrix

`tests/test_pipeline.py` provides focused durable control evidence:

- `test_failed_run_can_resume_from_completed_stage_checkpoints`
- `test_pause_requested_before_stage_stops_without_losing_prior_units`
- `test_pause_during_uninterruptible_stage_finishes_stage_then_pauses`
- `test_resume_after_restart_continues_from_durable_stage_boundaries`
- `test_cancel_during_tts_preserves_completed_units_and_stops_downstream`
- `test_cancelled_runs_cannot_resume`

The shared acceptance fixture additionally covers duplicate start, pause/resume, and cancel through production composition. Therefore the PRR-211 pause/resume/cancel/resume-after-failure matrix has focused regression evidence on the exact qualified head.

## R9 remaining reconciliation notes

The fresh-machine installed-wheel job deliberately uses installed package entry points rather than importing the repository test helper. That is the stronger isolation boundary for PRR-181's `Installed-wheel workflow where practical`; the reusable fixture family supplies equivalent deterministic setup for in-repository CLI/TUI/multi-episode acceptance while the fresh-machine script reconstructs the same public production workflow from the installed wheel.

One-off tests that retain independent lower-level contract coverage should not be removed merely to maximize fixture reuse. PRR-181's redundant-setup item is satisfied when redundant end-to-end setup is consolidated while focused unit/compatibility tests remain independent.

## Final qualification rule

The canonical TODO still must be reconciled on `master` and that reconciliation commit itself must receive exact-head CI. Only after reloading the reconciled TODO and companion spec from that exact head, confirming zero unchecked requirements, and observing successful `quality` plus `fresh-machine` jobs should PRR-221 and overall remediation be declared complete.
