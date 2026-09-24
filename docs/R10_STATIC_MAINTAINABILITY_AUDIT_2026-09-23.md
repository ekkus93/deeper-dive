# R10 Static Maintainability Audit — 2026-09-23

This note supports DDR-090 and DDR-091 in `docs/DEEP_DIVE_V1_INTEGRATION_REMEDIATION_TODO_2026-09-19.md`.

## Ruff exclusion audit

`pyproject.toml` has no project-level Ruff `exclude`, `extend-exclude`, `lint.extend-ignore`, or `lint.per-file-ignores` entries. The CI quality job therefore runs the configured formatter and lint gate across the full repository:

- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run mypy`
- `uv run pytest`
- `uv build`

The production modules called out by DDR-090 are included in those full-repository gates:

| Module | Audit result |
| --- | --- |
| `src/deeper_dive/audio_playback.py` | Included in Ruff/mypy. Retains one narrow inline `S603` suppression for fixed-argv `subprocess.Popen(..., shell=False)` playback launch. |
| `src/deeper_dive/cli.py` | Included in Ruff/mypy. No broad Ruff exception. |
| `src/deeper_dive/diagnostics.py` | Included in Ruff/mypy. No broad Ruff exception. |
| `src/deeper_dive/preflight.py` | Included in Ruff/mypy. No broad Ruff exception. |
| `src/deeper_dive/preflight_screen.py` | Included in Ruff/mypy. No broad Ruff exception. |
| `src/deeper_dive/transcript_review_screen.py` | Included in Ruff. It retains a narrow mypy `index` override in `pyproject.toml`; this is not a Ruff exclusion and does not bypass formatter or lint. |

There are no broad Ruff exclusions to remove. The remaining inline suppressions in production code are localized to specific provider/network/playback call sites with their rationale recorded next to the suppressed line. They do not exclude entire modules from lint or formatting.

## Composition/API duplication review

`ProductionComposition` is the production object graph used by the CLI and TUI surfaces. It constructs or exposes the shared services that the remediation work now routes through:

- provider configuration, factory construction, and registries;
- episode planning and effective provider/model assignment resolution;
- preflight services and controller boundaries;
- durable generation run repository and `PipelineOrchestrator`;
- episode export services and output identity;
- research analysis/execution controller boundaries;
- targeted transcript repair services;
- playback controller;
- TTS benchmark service.

Surface-specific command/screen code now calls into these shared services instead of owning independent shortcuts for planning, generation, export, provider inspection, research, or sanitizer behavior. Deterministic behavior remains behind explicit provider/service boundaries for tests and normal CI qualification, especially fake LLM/TTS providers and deterministic stage handlers used by the production-composed pipeline in credential-free environments.

The remediation evidence for R3 through R9 exercises this shared path from both TUI and CLI surfaces, including episode planning/generation/control/export, Quick Deep Dive, provider CLI inspection, research execution, and sanitizer/error handling.
