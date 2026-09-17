# Deeper Dive

Deeper Dive is a terminal-first, local-friendly application for turning a collection of documents into evidence-grounded research conversations and generated multi-host audio deep dives. The implementation follows the design and ordered task plan in `docs/`.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

## Install for development

```bash
uv sync --frozen
```

## Run

```bash
uv run deeper-dive --help
uv run deeper-dive --version
```

Importing `deeper_dive` is intentionally side-effect free: it does not contact providers, access the network, or download models.

## Quality checks

Run the complete local quality gate with:

```bash
./scripts/check.sh
```

That command checks formatting, Ruff lint, strict mypy typing, and pytest. Each stage exits nonzero on failure.

## Development status

The project is under active implementation. See `docs/DEEP_DIVE_TUI_SPEC.md` for the design authority and `docs/DEEP_DIVE_TUI_TODO.md` for qualification status.
