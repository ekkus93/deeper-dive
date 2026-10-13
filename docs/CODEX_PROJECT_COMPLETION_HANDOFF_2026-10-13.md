# Deeper Dive — Codex Project Completion Handoff

**Prepared:** 2026-10-13 (America/Los_Angeles)  
**Repository:** https://github.com/ekkus93/deeper-dive  
**Working branch:** `master` only; no branch/PR per task  
**Snapshot / last qualified implementation HEAD:** `bbd6083ae90bd883fcf4a8a322a195721c2a0a78`  
**Snapshot CI:** [Actions run 38480614517](https://github.com/ekkus93/deeper-dive/actions/runs/38480614517), **passed**  
**Current release version:** `0.1.0` (not a release-readiness claim)  
**Status:** Usable production-backed CLI and Textual workflows; **second post-review remediation is not finished**.

> **Codex's mission:** finish all still-open requirements in the **authoritative second post-review checklist**, preserve previously qualified behavior, perform an independent code/security review, and leave a fully evidence-reconciled, exact-head-CI-green `master`. The checklist, not this handoff, determines completion. Reload it before each work cluster and after every direct-master commit.

## 0. Read these files first (in order)

1. `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md` — **only authoritative completion checklist** for the current remediation cycle.
2. `docs/DEEP_DIVE_TUI_SECOND_POST_REVIEW_REMEDIATION_SPEC_2026-10-09.md` — normative SPR-01 through SPR-07 acceptance contract.
3. `docs/DEEP_DIVE_TUI_GUIDED_WORKFLOW_POST_REVIEW_REMEDIATION_TODO_2026-10-09.md` and its companion spec — previous **346/346 complete** cycle; historical regression obligations, **not** current completion.
4. `docs/DEEP_DIVE_TUI_SPEC.md` and `docs/DEEP_DIVE_TUI_TODO.md` — overall product architecture and earlier implementation roadmap.
5. `docs/ARCHITECTURE.md`, `docs/DEEP_DIVE_EPISODE_LIFECYCLE_CONTRACT_2026-10-10.md`, `docs/DEEP_DIVE_TYPED_DEFAULTS_CONTRACT_2026-10-10.md`, `docs/DEEP_DIVE_USER_DEFAULTS_V1_CONTRACT_2026-10-12.md`, `docs/PRODUCTION_GENERATION.md`, `docs/PRIVACY_SECURITY.md`, `docs/GUIDED_WORKFLOW_USER_GUIDE.md`, `docs/PROVIDERS.md`.
6. `.github/workflows/ci.yml` and `scripts/check.sh` — runnable qualification contract and installed-wheel gates.

**Hierarchy:** the present SPR TODO/spec overrides earlier checklists for current findings. Do not re-open/rewrite historical checked TODOs solely to fabricate progress. The older R4–R15 TUI/CLI/provider/qualification clusters are useful architectural context, not substitutes for satisfying this second review.

## 1. Verified state at handoff

| Property | Verified fact / limitation |
| --- | --- |
| `master` source HEAD before this documentation commit | `bbd6083ae90bd883fcf4a8a322a195721c2a0a78` |
| Existing head CI | [Run 38480614517](https://github.com/ekkus93/deeper-dive/actions/runs/38480614517) passed for that exact SHA |
| Quality job | `115581994418`: lock, Ruff format/lint, strict mypy, **2,085 passed** in pytest, source/wheel build, CLI/import smoke |
| Fresh-machine job | `115581994552`: clean wheel installation, CLI and Textual launch, production-style corpus/episode CLI flow, installed-wheel guided TUI and remediation matrix, **real KittenTTS Micro CPU smoke** passed |
| Current SPR TODO | **93 checked / 52 unchecked** (145 total) at source HEAD |
| Previous guided-workflow post-review TODO | **346 checked / 0 unchecked**; historical and previously reconciled |
| Branch/PR inventory | A first page of 100 branches existed, with a next cursor. Historical open PRs included #4, #14, #16, #18 and #104; inventory is **partial**, and these have not been established as applicable to current SPR work. Recheck before touching relevant code. |
| Deployment status | Neither a user-desktop signoff nor a production release is established by CI alone. |
| This file's own CI | **Not covered by the above passing run.** On commit, inspect new exact documentation-HEAD CI; if still pending/failed, the handoff commit is not itself qualified. |

Latest passing run: `https://github.com/ekkus93/deeper-dive/actions/runs/38480614517`. Its test total is **2,085 passed**, not the older 2,083 figure in an earlier evidence ledger entry. Exact counts may rise as tests are added.

**Do not call the project done because the latest CI passed.** That CI qualifies what is implemented at that SHA. The 52 unchecked obligations are independent.

### Current checklist distribution

| Section | Checked | Open | State |
| --- | ---: | ---: | --- |
| SPR-000 — baseline / reproduction evidence | 5 | **8** | Source/test inventory and shared fixture present; historical proof/disposition outstanding |
| SPR-100 — dirty wizard contract | 21 | **1** | Navigation regressions largely qualified; shared typed contract signoff outstanding |
| SPR-200 — durable host order | 11 | **0** | Reconciled, preserve with regression tests |
| SPR-300 — bounded readiness | 13 | **0** | Reconciled, preserve bounded-worker semantics |
| SPR-400 — semantic defaults | 8 | **4** | Cross-surface validation and table matrix incomplete |
| SPR-500 — atomic config persistence | 14 | **0** | Reconciled, preserve race/crash protections |
| SPR-600 — URL fragment/security | 5 | **4** | Mutated-model revalidation and broad canary coverage incomplete |
| SPR-700 — episode lifecycle | 13 | **3** | Cross-surface consistency/isolation/qualification incomplete |
| SPR-800 — preservation regression matrix | 3 | **8** | Broad end-to-end preservation proof outstanding |
| SPR-900 — independent review | 0 | **8** | Not yet reconciled |
| SPR-910 — final qualification | 0 | **16** | Not yet reconciled |
| **Total** | **93** | **52** | **In progress** |

These counts are a snapshot, not a commitment to check off items without new evidence. If `master` has moved, recalculate and prioritize based on the live TODO.

## 2. What the application already provides

Deeper Dive is a Python 3.12+ terminal-first, local-friendly, evidence-grounded document/research-to-audio application. It ships:
- **Textual GUI-in-terminal:** `deeper-dive-tui` with first-run setup, Home/Projects, New Deep Dive wizard, source/research/host/episode/plan steps, preflight, generation monitor, library, transcript review, targeted repair, playback, export.
- **JSON-capable CLI:** `deeper-dive` with `project`, `source`, `research`, `host` and `episode` commands. Creation, planning, generation, status/control, and export use shared production services where implemented.
- **Workspaces/persistence:** project-isolated SQLite records; durable episode configurations, segment plans, generation runs/checkpoints, transcripts, TTS artifacts and exports; versioned non-secret user config.
- **Providers:** fake deterministic LLM/TTS for CI; configurable local Ollama/llama-server and supported remote LLM/TTS integrations, including KittenTTS Micro CPU path; explicit model-role routing and local/remote preflight.
- **Security design:** credential environment-variable references rather than literal stored credential values; diagnostic/error sanitization, provider URL validation, typed defaults, controlled persistence.
- **Audio/export:** provider-backed generation and explicit artifacts: audio, transcript, manifest/provenance and metadata.

**Primary production boundaries to reuse instead of duplicating behavior:** `ProductionComposition` / `DeeperDiveService`; `EpisodeConfigurationService`, `EpisodePlannerService`, `PreflightService`, `PipelineOrchestrator`, `GenerationStartService`, `EpisodeExporter`; provider factory/registries and `ProviderController`; research services/controllers; `GuidedDraftStore`, `WizardShell` and concrete first-run/New Deep Dive wizards; `FirstRunReadinessCoordinator`; episode/library/repair controllers. Verify names and current call sites before refactoring.

### Source map

| Concern | Entry points / starting locations |
| --- | --- |
| CLI and package entry points | `src/deeper_dive/command.py`, `src/deeper_dive/cli.py` (if present), `pyproject.toml` |
| Guided Textual app and wizards | `src/deeper_dive/guided_app.py`, `wizard_shell.py`, `guided_first_run.py`, `guided_episode_wizard.py`, `guided_host_wizard.py`, `guided_source_wizard.py` |
| Providers/defaults/persistence | `src/deeper_dive/user_config.py`, `provider_tui.py`, `settings_screen.py`, `provider_factory.py` |
| Probe lifecycle | `src/deeper_dive/guided_async_readiness.py` and adapter I/O |
| Episode lifecycle and SQLite | `src/deeper_dive/episode_config.py`, `storage/episode_configuration.py`, `storage/episode_repositories.py` |
| Generation / exports | `src/deeper_dive/episode_planner.py`, generation/preflight/export services and `docs/PRODUCTION_GENERATION.md` |
| Security | `src/deeper_dive/diagnostics.py`, user-config and provider adapters, CLI/TUI error rendering |

## 3. Recent repair history: avoid regressions

The bridge was restarted, and GitHub App authentication/direct `master` commits worked again. An initial repair accidentally rewrote a **truncated** `wizard_shell.py` because an MCP `get_file` read window contained only the beginning of the tracked file; later exact-head CI exposed missing wizard subclasses. **This is now repaired and CI-qualified.** Critical lesson: **never upsert a file reconstructed from one bounded read without checking `total_lines`, `end_line` and reading every remaining page**, or use a complete local checkout.

Recent direct-master changes, in order:
- `bfb5c509575a7932938384ce13c1b41bd5a17c4a`: delayed-baseline test identity fixture + initial format repair.
- `c237ce1bca64c6b4019a156cea66002e74564ba7`: follow-on lint/format; the bounded-read omission was then discovered.
- `36068ba41e6ca7d7b3d143b7095ce2c65c395062`: restored complete wizard shell from the complete historical file and formatting.
- `107c30c0afe1560c0ccd9d405a93027d696d6f09`: restored `SetupMode` import.
- `adf270fe0bb4de46c6e32298084162d1669fdb8c`: restored `dataclasses.replace` import.
- `bbd6083ae90bd883fcf4a8a322a195721c2a0a78`: first-run recommended-role acceptance waits for production readiness after saving the provider; **exact-head CI fully passed**.

The complete installed-wheel run is evidence that both `NewDeepDiveWizardShell` and `FirstRunWizardShell` and their imports exist at the qualified HEAD. Do not treat those transient intermediate red CI runs as current defects; do review the resulting code for correctness as part of SPR-900.

## 4. Recommended Codex execution order

Work in coherent, dependency-first clusters, with focused tests **and** full exact-head CI at stable milestones. Do not create one branch, PR, or TODO-only commit per checkbox.

### A. Baseline evidence and typed wizard contract — SPR-000 + SPR-100 (9 open)

**Open:** SPR-000 historical proof/disposition for SPR-01/02/03/04/05/06 (7 reproducer bullets) plus unified finding disposition (1); SPR-100 shared typed dirty-form contract (1).

1. Compare the specific **reviewed baseline** `ce5eee194b7adcce4f077b04e7f9cdb1d7f7de5b` against current production implementation. Reproduce each suspected bug on the correct historical source where feasible **in isolated fixtures**; otherwise record narrowly justified, test-backed "disproved" or "needs-design" without asserting an incident. SPR-07's suspected no-op plan deletion/completed-state demotion was already tested and disproved in the TODO ledger.
2. Define/verify an explicit typed edit-session snapshot/identity contract: wizard kind, step, target project/episode/entity, last **durable** baseline, raw displayed values, semantic projection, and originally requested destination. Keep generation/refresh/selection races out of the durable baseline.
3. Revisit role recommendations, model discovery, source/host switching, custom durations and plan segment selections. Save/Discard/Cancel must protect typed edits; Cancel must be default focus; Escape must cancel; invalid/I/O-failed save must retain input; double submit must not act twice; clean navigation must remain frictionless.
4. Reuse existing production saves, not a parallel wizard-local persistence path. Only check the SPR-100 contract when implemented and proven by cross-step Textual tests and CI.

**Useful suites:** `tests/test_second_post_review_dirty_navigation.py`, `test_second_post_review_dirty_baseline.py`, `test_second_post_review_recommended_roles.py`, `test_second_post_review_first_run_form_matrix.py`, `test_second_post_review_new_deep_dive_form_matrix.py`, `test_post_review_dirty_save_exit.py`, `test_second_post_review_host_membership.py`, `test_second_post_review_model_discovery_dirty.py`.

### B. Typed defaults + credential/security convergence — SPR-400 + SPR-600 (8 open)

**SPR-400 (4):** shared normalization/validation in composite Settings, first-run, provider defaults and **actual** CLI mutation paths; no rejected settings/canary leak in exception/CLI/TUI; table-driven accepted/rejected/blank/legacy/restart with single-write/rollback checks; focused CI evidence/reconciliation.

**SPR-600 (4):** mutated Pydantic model revalidation before persistence from each surface; URL fragments/encoded separators/mixed case/partial malformed fake-canary matrix; inspection of stored JSON, nested diagnostics, exported bundles, CLI output and literal Textual rendered status; security-matrix CI evidence/reconciliation.

Use the authoritative `UserConfigStore.validate_candidate/save` boundary and `ProviderController` validation. Preserve legacy configs and safe blank-as-clear behavior; **never** publish partially validated provider runtime state or leak secrets in Pydantic location text/exceptions. The defaults schema is documented in `DEEP_DIVE_TYPED_DEFAULTS_CONTRACT_2026-10-10.md` and `DEEP_DIVE_USER_DEFAULTS_V1_CONTRACT_2026-10-12.md`.

**Scope caution:** Earlier contract notes observed no global-defaults CLI writer; inspect current CLI commands and do **not invent a fictitious CLI mutation path** to satisfy a checkbox. Explain and test each real reachable path, or add a real product-supported CLI surface only with a clear requirement. Preserve normal URL queries, IPv6, innocuous fragments in **diagnostics** (while forbidding endpoint URL fragments), and existing redaction semantics. Fake canaries only.

**Useful suites:** `tests/test_second_post_review_config_security.py`, `test_second_post_review_defaults_table_matrix.py`, `test_second_post_review_default_control_matrix.py`, `test_second_post_review_fragment_matrix.py`, `test_second_post_review_security_cross_surface.py`, `test_second_post_review_nested_url_redaction.py`, `test_second_post_review_encoded_url_diagnostics.py`, `test_second_post_review_controller_writer_races.py`, `test_second_post_review_config_fsync_matrix.py`.

### C. Episode lifecycle cross-surface proof — SPR-700 (3 open)

1. Verify the **same** lifecycle policy and actionable "create a new episode/revision" messaging across TUI, CLI, library, plan view, preflight, generate/control, playback, export. Completed and running episodes must not be silently demoted or lose their plan/history.
2. Add/reconcile multi-project, multi-episode isolation and Quick-vs-guided-vs-CLI acceptance using **one shared production fixture**. Assert persisted IDs, run state, plan identity, transcript/audio bytes and export manifest/metadata; restart; rejection of edits to completed/running historical episodes; legitimate draft edits invalidate only necessary plans.
3. Run the focused SPR-07 matrix and record exact-head CI, tests and appropriate N/A disposition for the disproved historical suspicions.

**Useful suites:** `tests/test_second_post_review_episode_lifecycle.py`, `test_second_post_review_cli_lifecycle_acceptance.py`, `test_second_post_review_tui_lifecycle_acceptance.py`, `test_second_post_review_tui_episode_lifecycle.py`, `test_second_post_review_acceptance_matrix.py`, `test_ddr104_multi_episode_isolation.py`.

### D. Full preservation regression matrix — SPR-800 (8 open)

Preserve and **demonstrate** the prior first-review improvements, not merely their existence:
1. PRR-100/110/120 sanitizer, credential references and cross-surface redaction.
2. PRR-200/210 dirty Save/Exit, safe drafts and stale-resume.
3. PRR-300/310/320 research precedence, non-default role discovery and async readiness.
4. PRR-400/410/420 host optional clears, destructive confirmations and atomic default saves.
5. Installed-wheel first-run/New Deep Dive end-to-end Textual, keyboard and compact-terminal behavior.
6. Quick path through `EpisodePlannerService`, production preflight, monitoring, transcript/review, targeted repair, playback, export.
7. CLI research and episode workflows, provider routing, Kitten benchmark, multi-episode isolation, pause/resume/cancel/status.
8. One expanded, deterministic security, dirty-form, concurrency, provider-routing and generation regression matrix.

**Fixture contract:** reuse `tests/conftest.py` fixtures `completed_episode_acceptance`, `two_project_completed_acceptance` and `second_post_review_acceptance` (inspect current definitions); they create actual projects, sources, hosts, fake LLM/TTS, plan, generation run, transcript, audio artifacts, export and a separate project through production services. Extend them rather than create unrelated mock-only acceptance worlds. Keep isolated temp workspaces, no real credentials/network or private corpus.

### E. Independent final review — SPR-900 (8 open)

Run an **independent second-pass source and test review**, with explicit notes/evidence for every checklist bullet:
- Changed call sites and production wiring; no unsound "helper exists" acceptance.
- Broad exception catches/swallowed failures and credential-bearing exception chains.
- Races at readiness worker publish, settings CAS swap, episode transactions, entity selection and dirty wizard forms.
- Keyboard/focus/Escape/modal cancellation, double actions, absent widgets, screen resume and viewport resizing.
- Migrations, older config compatibility, file/dir mode, fsync and symlink threat boundary.
- Tests that accidentally bypass production service paths, false positives or invalid "no errors" assertions.
- Remaining risks by severity; create actionable TODOs and fix **high/critical** findings before closeout.
- Explicit justification for every historical finding tagged N/A or disproved.

Record exact file/function/test identifiers, prior/after behavior and CI references in the authoritative TODO's evidence ledger. Avoid a code review that simply repeats previous checkbox claims.

### F. Final qualification and reconciliation — SPR-910 (16 open)

Finish *every* checkbox as written. Minimum sequence:
1. `uv lock --check`, `uv sync --frozen`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`.
2. `uv run pytest` — report accurate pass/fail/skip/xpass counts and investigate unexplained exceptions.
3. `uv build`; verify both source distribution and wheel; clean installed-wheel CLI import/help plus actual JSON project/source/research/host/episode commands.
4. Clean installed-wheel guided first-run/New Deep Dive/Quick Textual pilot on fake providers, plus configuration/security, dirty-navigation, host order, readiness, episode lifecycle and concurrent-writer matrices.
5. Real KittenTTS Micro CPU smoke in the fresh-machine gate as configured.
6. Verify baseline reproducers **fail before the corresponding fix and pass after** where possible; justify disproved/N/A cases.
7. Reconcile *each* outstanding checkbox with source/test references, exact SHA, CI run/job IDs and consistent count. Batch compatible reconciliation into coherent commits; **documentation-only commits still require their own exact-head CI pass**.
8. Re-read live `master` and both authoritative docs, confirm no unchecked or unqualified items remain, no missing alternate-branch changes, no unresolved high/critical findings; final **documentation head** must itself be green.

**Do not declare completion** with any unqualified open box, stale CI head, unrecorded acceptance result, or outstanding high/critical finding.

## 5. Exact qualification commands and workflow

Local setup:
```sh
uv python install 3.12
uv sync --frozen
uv lock --check
./scripts/check.sh
uv build
uv run deeper-dive --help
uv run deeper-dive-tui
```

Focused suites (examples; group by change):
```sh
uv run pytest tests/test_second_post_review_dirty_navigation.py tests/test_second_post_review_recommended_roles.py
uv run pytest tests/test_second_post_review_config_security.py tests/test_second_post_review_fragment_matrix.py
uv run pytest tests/test_second_post_review_episode_lifecycle.py tests/test_second_post_review_cli_lifecycle_acceptance.py
```

CI: `.github/workflows/ci.yml` has separate `quality` and `fresh-machine` jobs on `master` pushes. `quality` runs lock, formatting, lint, mypy, full pytest, package build and import/CLI smoke. `fresh-machine` builds and installs the wheel in a clean environment, exercises configured fake-provider CLI/episode output and guided Textual acceptance, runs an installed-wheel remediation matrix and real KittenTTS Micro CPU smoke. Check **both jobs** against **the exact SHA** of the final commit. Passing local tests or CI for a parent SHA is insufficient.

**Fresh-machine is authoritative for packaging/installability**, not just `uv run` in a developer virtualenv. The validated baseline was [CI 38480614517](https://github.com/ekkus93/deeper-dive/actions/runs/38480614517), quality job `115581994418` and fresh-machine job `115581994552`.

### Source control / multi-agent safety

- User preference: **work directly on `master`**; avoid per-task branches/PRs. If executing in a ChatGPT environment with Ralph Bridge, use Ralph Bridge for **all** GitHub/CI operations, with `commit_files` expected-head compare-and-swap. Codex running in its own checked-out environment may use its configured `git` remote, but should retain the same `master`-only/no-duplicate-work policy.
- On each run start and after each write: inspect exact remote `master` head, relevant open PRs/branches and CI; reload TODO/spec; reconcile concurrent work first. Existing old branches/PRs are not proof of unfinished SPR changes.
- No force push, ruleset bypass or wholesale rewrite of concurrent changes. On head drift fetch/rebase/reapply carefully or redo the exact-head CAS. Single logical commits are fine; avoid one reconciliation commit per checkbox.
- **Ralph read-window hazard:** inspect file size/line count and fetch every line window before writing a full-file body. The October 13 truncation incident is a real cautionary example.
- No external cloud credentials or user hardware should be needed for normal deterministic qualification. If a genuinely user-dependent blocker appears, describe exact missing authorization/asset and which unchecked items it blocks.

## 6. Completion evidence template (use in the authoritative TODO)

```text
Cluster / checklist items:
Baseline: historical SHA + reproducer/test (confirmed/disproved with rationale)
Production: paths:functions + durable effect + service boundaries
Tests: exact pytest node IDs; deterministic fixture; negative/rollback cases
Commit: exact full SHA on master
CI: exact-head run URL and quality/fresh-machine job IDs, conclusions
Security / compatibility / restart notes:
Remaining risks and disposition:
TODO reconciliation commit: exact SHA and its own passing CI:
```

Leave uncertain checkboxes unchecked. Do not imply every open item is a new known defect; several are evidence, integration, independent-review or final-signoff work.

## 7. Codex starting instruction

> Check out current `master` and read this handoff, the current second-post-review TODO and its companion spec. Inspect the current SHA, CI, relevant branches/PRs and existing test fixtures. Work directly on `master`, no branch or PR per subtask. Finish the 52 baseline-open items in dependency order: historical reproduction + typed dirty-form protocol; composite settings and URL/credential security; cross-surface episode lifecycle; preserved PRR/CLI/TUI/provider/Kitten matrices; independent review; final exact-head installed-wheel/quality CI and evidence reconciliation. Reuse production services and deterministic fixtures. Commit coherent clusters, diagnose and repair failures, re-read the TODO after each commit, and only check tasks when source + tests + exact-head CI + on-master integration prove acceptance. Never substitute old CI or a previous TODO's checked boxes for current proof. Stop only with fully qualified/reconciled `master` or a specific user-dependent blocker.

---

**Handoff provenance:** checked directly against Ralph Bridge `master`, the current authoritative TODO/spec, workflow and current CI on 2026-10-13. Snapshot counts and CI describe the implementation **before this new documentation commit**; verify the newest HEAD and its CI after committing this file.
