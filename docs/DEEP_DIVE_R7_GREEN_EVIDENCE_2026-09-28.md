# Deeper Dive R7 green evidence

Recorded: 2026-09-28

This note records exact-head evidence for the PRR-153 and R7 implementation cluster while the canonical TODO remains the completion source of truth.

## Head

- master SHA: `687f9c9b39dd805aece00a3cb824af3cd9faedce`
- CI run: `36472224044`
- CI conclusion: success
- Jobs observed: `quality` success and `fresh-machine` success

## Implemented cluster evidence

- PRR-153 public FFmpeg boundary: `FFmpegComposer.transcode_bytes` and public `run_command` are exercised through `tests/test_ffmpeg.py::test_transcode_bytes_uses_public_argv_boundary`; sanitized FFmpeg diagnostics are covered by `tests/test_ffmpeg.py::test_failure_sanitizes_stderr`.
- PRR-160 production repair recheck/update: production transcript repair no longer uses `_NoOpRepairRechecker` or `_NoOpSummaryUpdater`; repair now routes through material-claim extraction, evidence retrieval, structured verification, and conversation-state refresh.
- PRR-162 cache lifecycle: `TTSArtifactRepository` now collects obsolete physical files only after the last durable reference is removed, preserving shared and active artifacts.

## Focused tests in green run

- `tests/test_targeted_repair.py::test_targeted_repair_changes_only_affected_turn_and_rechecks`
- `tests/test_targeted_repair.py::test_repair_regenerates_changed_turn_without_breaking_shared_cache`
- `tests/test_targeted_repair.py::test_cache_cleanup_preserves_shared_file_until_last_reference_is_replaced`
- `tests/test_targeted_repair.py::test_repeated_unique_cache_replacement_collects_orphans`
- `tests/test_transcript_review_screen.py::test_transcript_review_default_repair_uses_production_service`
- `tests/test_transcript_review_screen.py::test_transcript_review_section_repair_uses_production_service`
- `tests/test_ffmpeg.py::test_transcode_bytes_uses_public_argv_boundary`
- `tests/test_ffmpeg.py::test_failure_sanitizes_stderr`

## Remaining R7 caution

The canonical TODO should not mark the remaining PRR-161 failure-sanitization and full TUI export-regression assertions complete until those exact assertions are landed and exact-head CI qualifies them.
