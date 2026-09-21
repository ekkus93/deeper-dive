# DDR-090 Ruff exclusion audit

**Date:** 2026-09-21  
**Scope:** Current state of `pyproject.toml` Ruff exclusions for `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md` DDR-090.

## Current `extend-exclude` inventory

The current Ruff `extend-exclude` list contains only test modules:

- `tests/test_cli.py`
- `tests/test_diagnostics.py`
- `tests/test_invalidation.py`
- `tests/test_preflight_routing.py`
- `tests/test_provider_cli.py`
- `tests/test_quick_deep_dive.py`

## Production module inventory requested by DDR-090

DDR-090 names these production modules for individual Ruff remediation or narrow retained-exception documentation:

- `src/deeper_dive/audio_playback.py`
- `src/deeper_dive/cli.py`
- `src/deeper_dive/diagnostics.py`
- `src/deeper_dive/preflight.py`
- `src/deeper_dive/preflight_screen.py`
- `src/deeper_dive/transcript_review_screen.py`

None of those production modules currently appears in the broad Ruff `extend-exclude` list. This means the remaining DDR-090 work should focus on direct per-module Ruff runs, fixes, and any narrow retained-exception notes rather than removing production paths from the global exclude list.

## Current retained exceptions

`pyproject.toml` still has one targeted mypy override for `deeper_dive.transcript_review_screen` disabling `index`. That is not a Ruff exclusion, but it remains relevant to DDR-090's maintainability audit and should be reviewed with the transcript review screen remediation work.

## Follow-up checklist

This document satisfies only the inventory step. Do not close DDR-090 until the named production modules have direct Ruff evidence, any necessary fixes are merged, formatter and mypy remain green, and broad exclusions are removed or explicitly narrowed where appropriate.
