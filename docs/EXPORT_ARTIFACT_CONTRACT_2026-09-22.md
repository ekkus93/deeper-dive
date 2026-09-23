# Export Artifact Contract

Created: 2026-09-22

This note documents the shared export contract used by the Episode Library, Transcript Review, CLI export remediation work, and later fresh-machine qualification. It supplements the V1 integration remediation TODO and should remain aligned with `EpisodeLibraryExportService` and `EpisodeExporter`.

## Scope

Episode export is a durable artifact workflow, not a status-message workflow. A successful export must write concrete files for one selected episode/run identity. A surface must not claim export success merely because it displayed an output directory, output label, or serialized episode metadata.

## Shared service boundary

All user-facing export surfaces should route through the shared episode export service or an equivalent composition-root service that produces the same artifact set and validation behavior. This applies to:

- Episode Library export.
- Transcript Review export/review artifact flows where applicable.
- CLI `episode export`.
- Installed-wheel and fresh-machine export qualification.

The service boundary must receive:

- the open `project_id`,
- the selected `EpisodeRecord`,
- the latest or explicitly selected `GenerationRunRecord`, and
- an optional output directory for CLI or test-controlled export destinations.

## Required validation

Export must fail explicitly when:

- the selected episode does not belong to the open project,
- no generation run exists for the episode,
- the selected run belongs to a different episode,
- the run is not in a completed/exportable state, or
- the completed episode has no transcript turns to export.

Errors surfaced through CLI/TUI entry points must pass through the canonical sanitizer before reaching users, logs, diagnostics, or persisted failure fields.

## Required artifact set

A successful export must create episode-specific files under the selected output directory:

1. Transcript Markdown: ordered host turns with host display names and turn text.
2. Source/provenance manifest JSON: included project sources with title, origin, and locator where available.
3. Metadata JSON: at minimum `project_id`, `episode_id`, `run_id`, title, and run state.
4. Audio file when episode audio exists for the selected episode identity.

The artifact names must include the selected episode identity or a collision-safe stem derived from the selected episode. A surface must not export or report artifacts from a different episode.

## Audio identity invariant

Audio export must resolve audio by the selected episode/run identity. Fallback behavior that scans for an arbitrary first audio file is not allowed. In a two-episode project, exporting episode A must never copy or report episode B audio.

## CLI output contract

The CLI should return machine-readable output when `--json` is supplied. The output should include the selected `episode_id` and concrete artifact paths such as:

```json
{
  "episode_id": "...",
  "transcript": "...md",
  "manifest": "...-sources.json",
  "metadata": "...-metadata.json",
  "audio": "...wav",
  "paths": ["...md", "...json", "...json", "...wav"]
}
```

For episodes without audio, `audio` may be `null`, but transcript, manifest, and metadata remain required for successful export.

## Qualification expectations

Tests for export remediation should assert file-system side effects and artifact contents, not only status text. At minimum, deterministic CI tests should assert:

- all reported paths exist,
- all reported paths are under the selected output directory when one is supplied,
- transcript content includes generated turn text,
- metadata contains the selected `episode_id` and `run_id`,
- manifest JSON preserves source/provenance fields, and
- exported audio bytes match the selected episode output when audio exists.

These expectations support DDR-031, DDR-063, DDR-101, DDR-104, DDR-111, DDR-120, DDR-121, DDR-132, and DDR-139 reconciliation.
