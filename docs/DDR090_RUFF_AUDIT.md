# DDR-090 Ruff exclusion audit

Current `pyproject.toml` has no production-module Ruff exclusions. The remaining `extend-exclude` entries are test modules only:

- `tests/test_cli.py`
- `tests/test_diagnostics.py`
- `tests/test_invalidation.py`
- `tests/test_preflight_routing.py`
- `tests/test_provider_cli.py`
- `tests/test_quick_deep_dive.py`

Therefore the production modules named by DDR-090 (`audio_playback.py`, `cli.py`, `diagnostics.py`, `preflight.py`, `preflight_screen.py`, and `transcript_review_screen.py`) are all covered by the repository-wide Ruff lint and Ruff format checks in normal CI. No retained production exception is required for those modules.

The repository-wide CI quality job also runs strict mypy. DDR-090 qualification is therefore the exact-head CI result for the commit carrying this audit, followed by merged-master CI.
