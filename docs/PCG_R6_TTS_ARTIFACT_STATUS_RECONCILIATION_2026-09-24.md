# PCG R6 TTS Artifact Status Reconciliation Evidence

This note accompanies the reconciliation of `docs/DEEP_DIVE_PRODUCTION_GENERATION_CORRECTNESS_TODO_2026-09-24.md` for R6.

## Scope

R6 covers `PCG-050` and `PCG-051`:

- Canonical TTS artifact success status selection.
- Repository/cache read compatibility for legacy success values.
- Save-time and persisted-row normalization to the canonical status.
- Production writer, installed-wheel smoke, CLI regression, and production-pipeline regression updates to use the canonical status.
- Legacy export/timeline/cache compatibility coverage.
- Guard coverage that the production TTS stage no longer writes the legacy success literal directly.

## Merged evidence

- PR #383 introduced `TTS_ARTIFACT_STATUS_COMPLETE`, legacy read compatibility, save-time normalization, and repository tests.
- PR #384 updated the production composition TTS writer, CLI generation test, production-pipeline artifact test, and fresh-machine workflow query to use the canonical status.
- PR #385 added persisted legacy-status normalization on `TTSArtifactRepository` construction.
- PR #388 added a workspace-level compatibility regression proving legacy `completed` artifacts remain cache-readable, timeline-visible, and exportable while reads normalize to canonical `complete`.

## Qualification

The latest merged master evidence commit for this cluster is `f3dafdc0096d25a662fb8fc7e589ed58e1adcf85`, with merged-master CI passing in run `35992678750`.
