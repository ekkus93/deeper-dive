# DDR-090 Ruff exclusion final evidence

**Date:** 2026-09-21

## Current state

`pyproject.toml` no longer defines `tool.ruff.extend-exclude`; the remaining test-file exclusions were removed through merged, exact-head-qualified PRs.

## Merged evidence

- PR #273, `DDR-090: include CLI tests in Ruff`, removed `tests/test_cli.py` from Ruff exclusions and passed merged-master CI at `aec5488e3097770c542c3898ed5de5f02c07d42f`.
- PR #275, `DDR-090: include provider CLI tests in Ruff`, removed `tests/test_provider_cli.py` from Ruff exclusions and passed merged-master CI at `e50fefb428e5657dc9a16ee1b90c20b6d24ac9fe`.
- PR #279, `DDR-090: include preflight routing tests in Ruff`, removed `tests/test_preflight_routing.py` from Ruff exclusions and passed merged-master CI at `16fde76c9c83cb937c4a43b7bf280591940275d3`.
- PR #280, `DDR-090: include quick deep dive tests in Ruff`, removed `tests/test_quick_deep_dive.py` from Ruff exclusions and passed merged-master CI at `9709a2b9356bfa22ccb969481176f35ece390425`.

## Qualification conclusion

The repository now runs Ruff format and Ruff lint without a broad Ruff exclusion list. This evidence supports DDR-090 reconciliation for the exclusion-removal and formatter-green portions. The TODO should still be reconciled conservatively where older checklist wording refers to historical production-module exclusions that are no longer present in `pyproject.toml`.
