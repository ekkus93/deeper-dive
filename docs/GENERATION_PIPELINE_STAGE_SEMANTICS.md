# Generation Pipeline Stage Semantics

The production generation pipeline is durable and ordered. A completed stage checkpoint means either that the stage performed its documented work, or that the stage crossed a documented boundary where no stage-specific work is currently required. Tests and user-facing documentation must not treat a boundary checkpoint as proof that unrelated artifacts exist.

## Current default stages

| Stage | Current handler | Semantics |
| --- | --- | --- |
| `sources` | durable boundary | Source ingestion and indexing are pre-generation readiness requirements. The generation pipeline does not import sources; completion means the run crossed this checkpoint after readiness passed. |
| `research` | durable boundary | Supplemental research is not currently executed by the generation pipeline. Completion is a checkpoint for future research work and resume/control ordering. |
| `planning` | production work when needed | If no plan exists, the stage builds one through `EpisodePlannerService` using the configured episode-planning provider assignment. Existing plans are reused. |
| `conversation` | production work when needed | If no turns exist, the stage calls the configured host-generation provider path and persists generated turns and provider identity evidence. Existing turns are reused. |
| `verification` | durable boundary | Claim verification is not currently executed as a standalone generation stage. Completion is a checkpoint for future verification work and resume/control ordering. |
| `tts` | production work when needed | The stage resolves each host's configured TTS provider/voice and routes synthesis through the shared TTS artifact/cache contract. |
| `composition` | production work when needed | The stage builds the audio timeline and episode-level audio from persisted TTS artifacts. |
| `export` | durable boundary | The stage marks generation as ready for explicit export. It does not write transcript, manifest, metadata, or export-package audio files. |

## Export contract

Generation completion and export artifacts are separate operations:

1. `episode generate` or the TUI monitor drives the pipeline through `export` and may leave a completed run at stage `export`.
2. `episode export` and Episode Library export are explicit export operations routed through `EpisodeLibraryExportService` / `EpisodeExporter`.
3. Export files are expected only after an explicit export call, not merely because the pipeline checkpoint named `export` completed.

This naming is intentionally preserved for compatibility with existing run-state displays, but documentation and tests must describe it as an export-readiness boundary rather than artifact export itself.
