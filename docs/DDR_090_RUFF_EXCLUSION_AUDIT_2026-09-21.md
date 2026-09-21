# DDR-090 Ruff exclusion audit

**Date:** 2026-09-21  
**Remediation area:** `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md` / DDR-090

## Current Ruff configuration

`pyproject.toml` configures Ruff with:

- `target-version = "py312"`
- `line-length = 100`
- lint rule families: `E`, `F`, `I`, `UP`, `B`, and `SIM`

The current broad `extend-exclude` list contains only test modules:

- `tests/test_cli.py`
- `tests/test_diagnostics.py`
- `tests/test_invalidation.py`
- `tests/test_preflight_routing.py`
- `tests/test_provider_cli.py`
- `tests/test_quick_deep_dive.py`

## Production-module audit result

DDR-090 names these production modules for explicit Ruff review:

- `src/deeper_dive/audio_playback.py`
- `src/deeper_dive/cli.py`
- `src/deeper_dive/diagnostics.py`
- `src/deeper_dive/preflight.py`
- `src/deeper_dive/preflight_screen.py`
- `src/deeper_dive/transcript_review_screen.py`

None of those production modules is currently excluded by `pyproject.toml` on `master` at `6f29bc1e39f0795cfef2248756d357466ef85e37`. That means normal Ruff configuration is already allowed to inspect those files unless a workflow invokes Ruff with a narrower target set.

## Remaining DDR-090 work

This audit satisfies the inventory/documentation part of DDR-090 only. DDR-090 should remain open until a follow-up implementation slice does all of the following:

1. Runs Ruff directly against each named production module.
2. Records the exact command/output evidence.
3. Removes or narrows any still-unneeded broad test exclusions.
4. Keeps formatter and mypy green on the exact head.

## Guardrail

Do not mark the production-module remediation checkboxes complete from this document alone. This file is an audit baseline for the subsequent code/configuration slices.
