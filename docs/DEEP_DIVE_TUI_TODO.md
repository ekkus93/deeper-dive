# Deeper Dive — Implementation TODO

**Companion design authority:** `docs/DEEP_DIVE_TUI_SPEC.md`  
**Implementation language:** Python 3.12+  
**Primary UI:** Textual TUI  
**Package/environment manager:** uv  

This document is the ordered implementation plan for Deeper Dive. It is intentionally detailed enough to drive autonomous implementation and review.

---

## 0. Execution rules and definition of done

### 0.1 Task status

Use these checkboxes as the authoritative task state:

- `[ ]` not complete
- `[x]` complete and qualified

Do not mark a task complete merely because code exists.

### 0.2 Qualification rule

A task is complete only when all of the following are true where applicable:

- implementation is present on the working branch;
- required tests exist;
- relevant tests pass;
- lint/format/type checks pass;
- failure paths have been considered;
- user-facing behavior matches the spec;
- documentation/config examples are updated;
- no known acceptance criterion is deferred without explicitly editing this TODO/spec;
- the change is merged to the default branch if execution is being performed through branches/PRs.

### 0.3 Exact-head rule

Milestone completion requires qualification at the exact commit being declared complete. A green workflow for an older commit is not sufficient evidence for a newer head.

### 0.4 Design consistency rule

If implementation discoveries require a material design change, update `docs/DEEP_DIVE_TUI_SPEC.md` in the same workstream before declaring the affected task complete.

### 0.5 No hidden provider dependencies

Normal CI must not require:

- OpenAI credentials;
- ElevenLabs credentials;
- a live Ollama instance;
- a live llama-server instance;
- live web-search APIs;
- KittenTTS model downloads;
- GPU hardware.

Use deterministic fake providers and fixtures in ordinary CI. Real-provider smoke tests must be opt-in.

### 0.6 Checkpoint safety rule

For long-running jobs, do not add UI progress that implies resumability until durable checkpoints actually exist for that stage.

### 0.7 Provenance rule

No task may collapse user-supplied and supplemental sources into an indistinguishable pool. Source origin must remain recoverable end-to-end.

---

# Milestone 1 — Repository and application foundation

## DD-001 — Bootstrap Python/uv project

- [ ] Create `pyproject.toml` for Python 3.12+.
- [ ] Establish `src/deeper_dive/` package layout.
- [ ] Add `uv.lock`.
- [ ] Add console entry point `deeper-dive`.
- [ ] Add development dependency groups for test/lint/type tooling.
- [ ] Add minimal README with install/run commands and project intent.
- [ ] Add `.gitignore` covering Python, local project state, caches, audio artifacts, secrets, and model weights.

**Acceptance criteria**

- `uv sync --frozen` succeeds on a clean supported machine.
- `uv run deeper-dive --help` exits successfully.
- Importing `deeper_dive` has no network or model-download side effects.

## DD-002 — Establish code quality tooling

- [ ] Configure Ruff formatting/linting.
- [ ] Select and configure mypy or Pyright.
- [ ] Configure pytest.
- [ ] Add common developer commands/scripts.
- [ ] Add pre-commit configuration if it improves local consistency without becoming required infrastructure.

**Acceptance criteria**

- One documented command runs format check, lint, type check, and tests.
- Intentional lint/type/test failures produce nonzero exits.

## DD-003 — Add baseline GitHub Actions CI

- [ ] Add workflow for dependency lock validation.
- [ ] Add Ruff check.
- [ ] Add static type check.
- [ ] Add pytest.
- [ ] Add package build/import smoke test.
- [ ] Cache dependencies appropriately without masking lock drift.

**Acceptance criteria**

- Fresh CI succeeds from a clean checkout with no external credentials.
- CI fails on a deliberately invalid formatting/type/test fixture in local validation or a temporary test commit.

## DD-004 — Core IDs, errors, and clock abstractions

- [ ] Define stable ID helpers/types for Project, Source, Chunk, Host, Episode, Turn, Run, etc.
- [ ] Define structured application exception hierarchy.
- [ ] Introduce injectable clock/time helper where timestamps affect tests.
- [ ] Define serialization rules for IDs and timestamps.

**Acceptance criteria**

- IDs round-trip through domain serialization.
- Error classes distinguish user/config/provider/storage/recoverable failures.
- Timestamp-dependent tests are deterministic.
