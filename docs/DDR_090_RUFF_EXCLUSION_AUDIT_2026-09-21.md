# DDR-090 Ruff exclusion audit — 2026-09-21

## Current configuration

`pyproject.toml` has no Ruff exclusions for production modules. The current `extend-exclude` list contains only these test modules:

- `tests/test_cli.py`
- `tests/test_diagnostics.py`
- `tests/test_invalidation.py`
- `tests/test_preflight_routing.py`
- `tests/test_provider_cli.py`
- `tests/test_quick_deep_dive.py`

Therefore the production modules named by DDR-090 — `audio_playback.py`, `cli.py`, `diagnostics.py`, `preflight.py`, `preflight_screen.py`, and `transcript_review_screen.py` — are all inside the normal Ruff target set. There is no broad production exclusion left to retain or narrow.

## Qualification

The normal repository CI runs Ruff, formatting, mypy, and tests against the production tree. DDR-090 should be considered satisfied when exact-head CI remains green with this configuration: production code is not excluded, so each named module is covered by the ordinary Ruff invocation rather than requiring a separate exclusion-specific command.

The remaining `extend-exclude` entries are test-only technical debt and are not production-module exclusions. They should be handled separately rather than reintroducing a production exception.
