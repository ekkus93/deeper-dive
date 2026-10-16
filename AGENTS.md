# Repository Guidelines

## Project Structure & Module Organization

The installable Python package lives in `src/deeper_dive/`. Keep domain rules in `domain/`, application orchestration in `application/`, and persistence concerns in `storage/`; the remaining modules provide CLI, Textual UI, provider, and media features. Tests live in `tests/`, with reusable inputs under `tests/fixtures/`. Product contracts and developer references live in `docs/`; `scripts/` contains repository maintenance commands. Avoid committing generated caches or local runtime data.

## Build, Test, and Development Commands

- `uv sync --frozen` installs the locked runtime and development dependencies.
- `uv run deeper-dive --help` shows CLI commands; `uv run deeper-dive-tui` starts the interactive app.
- `uv run pytest` runs the full test suite. Run a focused file with `uv run pytest tests/test_cli.py`.
- `./scripts/check.sh` runs the repository quality gate: Ruff format check, Ruff lint, strict mypy, then pytest.
- `uv run ruff format .` formats Python files; `uv run ruff check .` reports lint issues.

## Coding Style & Naming Conventions

Use Python 3.12 features, four spaces, double quotes, and a 100-character line limit. Ruff enforces formatting and the configured `E`, `F`, `I`, `UP`, `B`, and `SIM` rules; mypy runs in strict mode. Keep type annotations explicit. Use `snake_case` for modules, functions, and variables, and `PascalCase` for classes. Follow the existing separation between domain, application, and storage code.

## Testing Guidelines

Pytest is configured to discover `tests/` and uses strict markers/configuration. Name test modules `test_<behavior>.py` and tests `test_<expected_behavior>`. Prefer deterministic tests with fake providers and fixtures; ordinary tests should not require live services, credentials, network access, or model downloads. Add regression coverage for behavior changes and run the focused tests before `./scripts/check.sh` when practical.

## Commit & Pull Request Guidelines

Recent history uses Conventional Commit-style prefixes such as `fix:`, `test:`, and `docs:` followed by a concise summary; preserve that pattern. Pull requests should explain the user-visible or architectural change, link relevant issues or plan items, note validation commands and results, and include terminal captures for visible TUI changes. Update the relevant docs when changing behavior or product contracts.

## Configuration & Privacy

Keep credentials out of source control, project databases, exports, and diagnostic output. Use the documented provider and environment configuration paths in `docs/PROVIDERS.md`; review `docs/PRIVACY_SECURITY.md` when touching source handling, provider routing, or diagnostics. Normal development and tests should use fake providers.
