# DDR-031 Export Reconciliation Evidence

This note records the merged evidence for `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md` / DDR-031, `Episode Library real Export`.

## Current merged implementation

DDR-031 is implemented by the shared `EpisodeLibraryExportService`, which is used by Episode Library export surfaces and is backed by the common `EpisodeExporter` artifact writer.

The service enforces the production export contract before writing artifacts:

- the selected episode must belong to the open project;
- the selected generation run must exist;
- the generation run must belong to the selected episode;
- the generation run must be `completed`;
- the completed episode must contain transcript turns.

A successful export writes concrete episode-specific artifacts rather than a status label:

- transcript markdown;
- source/provenance manifest JSON;
- metadata JSON containing project, episode, run, title, and run state;
- selected-episode audio when `output/<episode_id>.mp3` or `output/<episode_id>.wav` exists.

The audio copy path is keyed by selected `episode_id`, preserving the artifact-identity invariant documented in `docs/EXPORT_ARTIFACT_CONTRACT_2026-09-22.md`.

## Merged qualification

PR #333 merged as `2ca5a1550e173e8e1a4ba3b38f63cd07e2756115` and added production-composition coverage for the full artifact set.

The qualifying test proves that a production-composed deterministic episode export produces:

- real filesystem transcript, manifest, metadata, and audio files;
- transcript content containing the generated deterministic turn text;
- manifest content with selected source/provenance information;
- metadata content for the selected project, episode, and run;
- deterministic audio bytes tied to the selected episode;
- explicit rejection of missing or non-completed runs.

The same PR also fixed a production retrieval defect discovered by the export workflow: natural-language search text containing punctuation is now converted into syntax-safe FTS5 terms before querying, and regression coverage protects that path.

## CI evidence

- PR #333 exact-head CI passed on `d63af6abcf04eefe178d099ea792f2b5dc15a9f6`.
- Merged-`master` CI passed on `2ca5a1550e173e8e1a4ba3b38f63cd07e2756115`.

## TODO reconciliation implication

DDR-031 is ready for a TODO reconciliation update marking these checklist items complete:

- Invoke shared EpisodeExporter.
- Produce actual episode-specific artifacts.
- Report concrete produced paths/artifacts.
- Handle incomplete/unexportable episodes explicitly.
- Replace status-text-only test with filesystem/artifact assertions.

The acceptance criterion is satisfied because the merged test asserts real files and artifact contents; an output-directory/status-label-only implementation would fail the test.
