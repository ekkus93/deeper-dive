# Static Analysis Audit — 2026-09-22

This note records the DDR-090 audit against the exact `master` baseline `66f4017c3811604350e8dd340c92fdae796c846b`.

## Ruff configuration

`pyproject.toml` contains one global Ruff configuration for Python 3.12 with `E`, `F`, `I`, `UP`, `B`, and `SIM` enabled. It contains no `per-file-ignores`, `exclude`, or `extend-exclude` entries. Therefore there are currently **no production modules excluded from Ruff**.

The modules named by DDR-090 are consequently all covered by the ordinary global Ruff invocation rather than narrow exceptions:

- `src/deeper_dive/audio_playback.py`
- `src/deeper_dive/cli.py`
- `src/deeper_dive/diagnostics.py`
- `src/deeper_dive/preflight.py`
- `src/deeper_dive/preflight_screen.py`
- `src/deeper_dive/transcript_review_screen.py`

No retained Ruff exception is required for any of these modules on the audited baseline.

## Formatter and mypy

Ruff formatting is configured globally with the project line length and double-quote policy. Mypy is strict for the `deeper_dive` package. The only current mypy override is a narrow `index` diagnostic suppression for `deeper_dive.transcript_review_screen`; this is a mypy override, not a Ruff exclusion.

## Qualification rule

DDR-090 should be reconciled only after exact-head CI for the commit carrying this audit passes. That CI is the executable evidence that the globally covered modules remain Ruff-clean, formatter-clean, and compatible with the project's mypy gate at the audited head. Any future broad Ruff exclusion should be treated as a regression against this audit and must be explicitly justified.