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

- [x] Create `pyproject.toml` for Python 3.12+.
- [x] Establish `src/deeper_dive/` package layout.
- [x] Add `uv.lock`.
- [x] Add console entry point `deeper-dive`.
- [x] Add development dependency groups for test/lint/type tooling.
- [x] Add minimal README with install/run commands and project intent.
- [x] Add `.gitignore` covering Python, local project state, caches, audio artifacts, secrets, and model weights.

**Acceptance criteria**

- `uv sync --frozen` succeeds on a clean supported machine.
- `uv run deeper-dive --help` exits successfully.
- Importing `deeper_dive` has no network or model-download side effects.

## DD-002 — Establish code quality tooling

- [x] Configure Ruff formatting/linting.
- [x] Select and configure mypy or Pyright.
- [x] Configure pytest.
- [x] Add common developer commands/scripts.
- [x] Evaluate pre-commit configuration; intentionally omit it because `scripts/check.sh` plus CI provide the consistency gate without adding required local infrastructure.

**Acceptance criteria**

- One documented command runs format check, lint, type check, and tests.
- Intentional lint/type/test failures produce nonzero exits.

## DD-003 — Add baseline GitHub Actions CI

- [x] Add workflow for dependency lock validation.
- [x] Add Ruff check.
- [x] Add static type check.
- [x] Add pytest.
- [x] Add package build/import smoke test.
- [x] Cache dependencies appropriately without masking lock drift.

**Acceptance criteria**

- Fresh CI succeeds from a clean checkout with no external credentials.
- CI fails on a deliberately invalid formatting/type/test fixture in local validation or a temporary test commit.

## DD-004 — Core IDs, errors, and clock abstractions

- [x] Define stable ID helpers/types for Project, Source, Chunk, Host, Episode, Turn, Run, etc.
- [x] Define structured application exception hierarchy.
- [x] Introduce injectable clock/time helper where timestamps affect tests.
- [x] Define serialization rules for IDs and timestamps.

**Acceptance criteria**

- IDs round-trip through domain serialization.
- Error classes distinguish user/config/provider/storage/recoverable failures.
- Timestamp-dependent tests are deterministic.

---

# Milestone 2 — Persistence and workspace

## DD-010 — Data-directory and workspace management

- [x] Implement platform-appropriate default data directory.
- [x] Support explicit data-directory override.
- [x] Create project workspace layout from the spec.
- [x] Sanitize generated path components.
- [x] Prevent path traversal outside project workspace.

**Acceptance criteria**

- Creating two projects produces isolated workspaces.
- Malicious or unusual project names cannot escape the configured data directory.

## DD-011 — SQLite database foundation

- [x] Add SQLite connection/session abstraction.
- [x] Enable safe transaction handling.
- [x] Choose and implement migration strategy.
- [x] Add initial schema version table.
- [x] Configure foreign keys and appropriate journal/busy behavior.

**Acceptance criteria**

- Fresh database initializes automatically.
- Reopening an initialized database is idempotent.
- A migration test proves an older fixture database can advance safely.

## DD-012 — Persist core project/source models

- [x] Persist Project metadata.
- [x] Persist Source metadata/origin/status.
- [x] Persist SourceChunk metadata.
- [x] Add repository/data-access layer; business logic must not embed ad hoc SQL throughout the codebase.
- [x] Add create/read/update/list/delete operations required by later milestones.

**Acceptance criteria**

- Project/source data survives process restart.
- User vs supplemental origin survives full database round trip.
- Foreign-key deletion behavior is explicitly tested.

## DD-013 — Persist hosts and episodes

- [x] Persist HostProfile.
- [x] Persist host relationships.
- [x] Persist Episode configuration.
- [x] Persist ordered episode host membership.
- [x] Persist EpisodePlan/SegmentPlan schema placeholders sufficient for later migration-free evolution where practical.

**Acceptance criteria**

- Multi-host order and relationships round-trip exactly.
- Multiple episodes can reference the same project corpus independently.

## DD-014 — Generation-run/checkpoint persistence

- [x] Persist GenerationRun.
- [x] Persist stage state.
- [x] Persist completed work-unit identifiers.
- [x] Persist sanitized failure diagnostics and retry counters.
- [x] Add pause/cancel flags/state.

**Acceptance criteria**

- Killing/reopening a test process preserves the last committed stage/unit.
- Replaying a completed checkpoint is idempotent.

---

# Milestone 3 — Application service, CLI shell, and Textual shell

## DD-020 — Application service boundary

- [x] Create application/service layer used by all clients.
- [x] Define commands/use cases for projects, sources, hosts, episodes, providers, and runs.
- [x] Define event/progress interface suitable for TUI and CLI.
- [x] Ensure UI modules have no direct provider calls.

**Acceptance criteria**

- A headless test can create/open a project using the service layer only.
- Dependency-direction test/review confirms TUI does not import concrete provider adapters directly.

## DD-021 — CLI skeleton

- [x] Implement `deeper-dive --help` and version output.
- [x] Add project create/list/open-info commands.
- [x] Add `--json` output pattern for automation-friendly commands.
- [x] Establish consistent exit codes and stderr/stdout behavior.

**Acceptance criteria**

- CLI integration tests create and inspect a project in a temporary data directory.
- JSON mode emits valid JSON without decorative terminal text.

## DD-022 — Textual application shell

- [x] Add Textual app entry point.
- [x] Add Home/Projects screen shell.
- [x] Add global navigation to Providers, Settings, Help.
- [x] Add project top navigation: Sources, Research, Hosts, Episode, Generate, Library.
- [x] Add command palette and discoverable keyboard shortcuts.
- [x] Add responsive behavior for narrow terminals.

**Acceptance criteria**

- Textual pilot tests navigate all shell screens.
- Basic navigation works at 80x24 without uncaught exceptions.
- State is not encoded by color alone.

## DD-023 — Home/Projects workflow

- [x] New project dialog.
- [x] Project list with modified time/status/count placeholders.
- [x] Open project.
- [x] Rename project.
- [x] Delete project with confirmation.
- [x] Surface interrupted/paused run state.

**Acceptance criteria**

- All operations use application services.
- TUI tests cover create/open/rename/delete/cancel-delete.

---

# Milestone 4 — Source ingestion

## DD-030 — Parser abstraction

- [x] Define parser contract and parse result model.
- [x] Preserve structural/location metadata where available.
- [x] Define parse warning/error reporting.
- [x] Store parser identity/version for cache invalidation.

**Acceptance criteria**

- Fake parser contract test demonstrates deterministic parse/chunk metadata flow.

## DD-031 — Plain text and Markdown ingestion

- [x] Parse `.txt`.
- [x] Parse `.md` as text while retaining headings where practical.
- [x] Support pasted text source.
- [x] Compute content hashes.

**Acceptance criteria**

- Tests cover UTF-8, unusual Unicode, empty files, malformed/unsupported encoding handling, and duplicate content.

## DD-032 — PDF ingestion

- [x] Select maintained PDF text extraction library.
- [x] Extract per-page text where reliably possible.
- [x] Preserve page provenance.
- [x] Surface extraction warnings for image-only/unreadable PDFs.
- [x] Do not silently OCR in V1 unless explicitly added to spec/TODO.

**Acceptance criteria**

- Multi-page fixture preserves page numbers.
- Image-only fixture produces clear warning rather than fabricated text.

## DD-033 — DOCX ingestion

- [x] Extract paragraphs/headings.
- [x] Preserve useful section metadata.
- [x] Handle malformed DOCX cleanly.

**Acceptance criteria**

- Fixture round-trips title/headings/body into normalized parse output.

## DD-034 — HTML/file and URL ingestion

- [x] Parse local HTML.
- [x] Fetch explicit HTTP/HTTPS user URLs with timeout/size limits.
- [x] Extract readable main text where practical.
- [x] Record original/final canonical URL and retrieval timestamp.
- [x] Distinguish explicit user URL fetching from automated research-network policy.

**Acceptance criteria**

- Redirect, timeout, oversized response, non-HTML text response, and HTTP error tests exist.
- URL content retains `user` source origin when explicitly added by the user.

## DD-035 — Directory/batch import and deduplication

- [x] Add multiple files.
- [x] Add directory recursively with supported-extension filtering.
- [x] Detect exact duplicate content by hash.
- [x] Detect duplicate canonical URLs.
- [x] Present duplicate disposition to user rather than silently duplicating.

**Acceptance criteria**

- Importing same corpus twice does not create duplicate active sources by default.

## DD-036 — Chunking

- [x] Implement deterministic baseline chunker.
- [x] Preserve source/page/heading provenance.
- [x] Add configurable chunk-size/overlap internals with sensible defaults.
- [x] Version chunking configuration.

**Acceptance criteria**

- Re-chunking same input/config produces stable chunk boundaries and IDs or stable deterministic mapping.
- No chunk can lose its source origin/location.

## DD-037 — Sources TUI screen

- [x] Implement primary/supplemental grouped source list.
- [x] Implement source details pane.
- [x] Add files/directory/URL/paste actions.
- [x] Include/exclude action.
- [x] Delete action.
- [x] Parsed-text inspection.
- [x] Metadata/provenance inspection.
- [x] Visible parse/index/error states.

**Acceptance criteria**

- TUI tests cover successful import, duplicate, parse warning, exclusion, deletion, and source inspection.

---

# Milestone 5 — Retrieval and evidence

## DD-040 — Lexical index

- [x] Implement persistent lexical/BM25-style search over included chunks.
- [x] Incrementally update when sources change.
- [x] Return scored stable chunk IDs.
- [x] Filter excluded sources.

**Acceptance criteria**

- Retrieval fixture returns expected relevant chunks.
- Excluded source never appears in normal retrieval.

## DD-041 — Embedding provider abstraction

- [x] Define embedding provider contract.
- [x] Define embedding model metadata/capabilities.
- [x] Add deterministic fake embedding provider for tests.
- [x] Persist embedding model/config identity with vectors.

**Acceptance criteria**

- Switching embedding model invalidates/rebuilds only incompatible vectors.

## DD-042 — Initial embedding backends

- [x] Add OpenAI embeddings adapter.
- [x] Add Ollama/local adapter if supported cleanly by selected Ollama API.
- [x] Add local sentence-transformer style backend or explicitly defer it by updating spec/TODO with rationale.

**Acceptance criteria**

- Each adapter has contract tests using mocks/fixtures.
- Real credentials/models are unnecessary in CI.

## DD-043 — Persistent vector index

- [x] Select lightweight local vector storage/index strategy appropriate for Python desktop use.
- [x] Persist vectors.
- [x] Support incremental add/remove/rebuild.
- [x] Preserve chunk IDs and provider/model version.

**Acceptance criteria**

- Restart does not require recomputing unchanged vectors.

## DD-044 — Hybrid retrieval and fusion

- [x] Combine lexical and vector candidates.
- [x] Implement rank fusion.
- [x] Add reranker interface.
- [x] Implement baseline reranker/heuristic.
- [x] Return explicit retrieval metadata.

**Acceptance criteria**

- Tests prove lexical-only mode works with no embeddings configured.
- Hybrid mode retains provenance through fusion/reranking.

## DD-045 — Claim/evidence domain persistence

- [x] Persist Claim.
- [x] Persist Evidence links.
- [x] Support supports/contradicts/contextualizes/uncertain relations.
- [x] Store retrieval/verification metadata without overwriting source provenance.

**Acceptance criteria**

- One claim can be linked to supporting and contradicting evidence simultaneously.

---

# Milestone 6 — LLM provider subsystem

## DD-050 — LLM provider contract and registry

- [x] Implement normalized `LLMProvider` contract.
- [x] Define request/response/stream types.
- [x] Define capability metadata.
- [x] Define provider registry/configuration.
- [x] Implement health/model-discovery operations.
- [x] Add deterministic fake LLM provider.

**Acceptance criteria**

- Orchestration code depends on interface/registry, not concrete providers.
- Fake provider can deterministically drive integration tests.

## DD-051 — OpenAI LLM provider

- [x] Implement supported OpenAI generation path using the current official API/library chosen at implementation time.
- [x] Support structured output where available.
- [x] Support streaming where useful.
- [x] Normalize usage/latency/errors.
- [x] Apply bounded timeout/retry behavior.

**Acceptance criteria**

- Mock contract tests cover success, structured output, stream, timeout, rate limit, auth error, malformed response.

## DD-052 — Ollama provider

- [x] Implement native Ollama adapter.
- [x] Model discovery.
- [x] Health check.
- [x] Generation.
- [x] Structured-output strategy where supported.
- [x] Capture relevant context/capability metadata when available.

**Acceptance criteria**

- Mock native Ollama API tests pass.
- Provider works independently of OpenAI compatibility mode.

## DD-053 — llama-server provider

- [x] Implement native llama-server adapter.
- [x] Health/model discovery as exposed by the server.
- [x] Generation/streaming.
- [x] Structured-output strategy.
- [x] Handle configurable base URL and endpoint differences cleanly.

**Acceptance criteria**

- Mock llama-server tests cover common success/error shapes.
- Local server unavailability is a recoverable configuration/provider error.

## DD-054 — Model role assignments

- [ ] Add user-level defaults.
- [ ] Add project-level assignments.
- [ ] Add episode overrides.
- [ ] Roles include corpus analysis, research planning, source analysis, episode planning, directing, host generation, verification.
- [ ] Implement documented precedence.

**Acceptance criteria**

- Tests prove episode > project > user precedence.
- Preflight can resolve every required role to provider+model or report a blocker.

## DD-055 — Structured-output validation/repair

- [ ] Centralize Pydantic-based structured response validation.
- [ ] Add bounded retry/repair strategy.
- [ ] Persist sanitized validation failures for diagnosis.
- [ ] Never commit partially invalid objects to durable final state.

**Acceptance criteria**

- Invalid JSON/schema responses cannot corrupt an episode plan or research gap list.

---

# Milestone 7 — Provider configuration and secrets

## DD-060 — User configuration model

- [ ] Add user config storage separate from project data.
- [ ] Store endpoints, defaults, and non-secret provider settings.
- [ ] Add config schema versioning.
- [ ] Add clear validation messages.

**Acceptance criteria**

- Invalid provider endpoint/model config fails before expensive generation.

## DD-061 — Secret storage abstraction

- [ ] Define credential store interface.
- [ ] Implement OS keyring backend where practical.
- [ ] Support environment-variable credential references/fallback.
- [ ] Ensure secrets never serialize into project config/database diagnostics.
- [ ] Add centralized redaction utility.

**Acceptance criteria**

- Automated tests scan representative logs/config/diagnostics and find no injected test secret.

## DD-062 — Providers TUI screen

- [ ] List configured LLM and TTS providers separately.
- [ ] Add/edit/remove provider config.
- [ ] Test/health action.
- [ ] Discover models.
- [ ] Discover voices for TTS-capable providers.
- [ ] Display capabilities and actionable errors.

**Acceptance criteria**

- TUI tests configure a fake provider and successfully run health/discovery actions.

---

# Milestone 8 — Supplemental research

## DD-070 — Research policy model

- [ ] Implement Off, Conservative, Useful, Aggressive modes.
- [ ] Implement independent behavior toggles from spec.
- [ ] Add project defaults and episode overrides.

**Acceptance criteria**

- Off mode performs zero automated web searches.
- Policy state survives restart.

## DD-071 — Corpus analysis and research-gap planner

- [ ] Build structured corpus summary inputs.
- [ ] Generate `ResearchGap` objects with category, rationale, priority.
- [ ] Link gaps to relevant existing sources/chunks.
- [ ] Detect at least missing context, disagreement, recency, and cited-but-missing categories where evidence permits.
- [ ] Persist gap state.

**Acceptance criteria**

- Deterministic fake-LLM fixture produces persisted, inspectable gaps.
- No search occurs merely as a side effect of generating gaps.

## DD-072 — Search provider abstraction

- [ ] Define search query/result provider contract.
- [ ] Define fetch/extraction contract separately from search.
- [ ] Add deterministic fake search provider.
- [ ] Make query purpose/research-gap ID mandatory in automated research path.

**Acceptance criteria**

- Automated search call without a research-gap/research-question association is rejected by the service layer.

## DD-073 — Initial public web search implementation

- [ ] Select an initial supported search backend suitable for the project.
- [ ] Implement result normalization.
- [ ] Apply configurable query/result bounds.
- [ ] Handle provider errors/rate limits cleanly.
- [ ] Document optional credentials or terms if required.

**Acceptance criteria**

- Live search is not needed in normal CI.
- Fake integration test drives full gap → search-results path.

## DD-074 — Research-safe web fetcher

- [ ] HTTP/HTTPS only for automated research.
- [ ] DNS/IP checks preventing private/link-local/loopback automated fetches.
- [ ] Redirect revalidation.
- [ ] Timeouts.
- [ ] Maximum response size.
- [ ] Content-type validation.
- [ ] HTML/text extraction.
- [ ] Canonical URL tracking.

**Acceptance criteria**

- SSRF-oriented tests cover loopback, private IPv4/IPv6, redirect-to-private, oversized body, timeout, invalid scheme.

## DD-075 — Candidate evaluation and deduplication

- [ ] Evaluate relevance to gap.
- [ ] Detect source/content duplicates.
- [ ] Capture publication/source metadata where possible.
- [ ] Rank authority/quality with domain-sensitive heuristics and/or LLM assistance.
- [ ] Record rejection reason.
- [ ] Record accepted-source inclusion reason.

**Acceptance criteria**

- Every accepted supplemental source has origin=`supplemental` and at least one motivating gap/reason.
- Rejected candidates remain inspectable at least for the run/history needed by Research UI.

## DD-076 — Research TUI screen

- [ ] Policy selector.
- [ ] Behavior toggles.
- [ ] Research-focus editor.
- [ ] Analyze corpus/find gaps action.
- [ ] Gap list with priority/status/rationale.
- [ ] Search/Ignore per gap.
- [ ] Research-all-selected action.
- [ ] Progress.
- [ ] Candidate accepted/rejected summary.
- [ ] Navigation to supplemental Sources.

**Acceptance criteria**

- TUI test demonstrates gap analysis, ignore, research, accepted supplemental source, and provenance inspection using fakes.

---

# Milestone 9 — Host subsystem

## DD-080 — Host preset definitions

- [ ] Implement Curious Explainer.
- [ ] Implement Skeptic.
- [ ] Implement Synthesizer.
- [ ] Implement Domain Expert.
- [ ] Implement Practitioner.
- [ ] Implement Historian.
- [ ] Implement Moderator.
- [ ] Implement Custom baseline.
- [ ] Keep presets as data/configurable factories rather than hard-coded branching across engine code.

**Acceptance criteria**

- Preset profiles serialize to normal editable HostProfiles.
- Editing a preset-derived host does not mutate global preset defaults.

## DD-081 — Host behavior model

- [ ] Add trait validation/ranges.
- [ ] Add role/expertise/custom instructions.
- [ ] Add evidence priorities.
- [ ] Add turn-length/question/analogy/interruption preferences.
- [ ] Add host relationships.

**Acceptance criteria**

- Three-host relationship graph persists and is usable by prompt assembly.

## DD-082 — Hosts TUI screen

- [ ] Host list and editor panes.
- [ ] Add preset/custom host.
- [ ] Duplicate.
- [ ] Remove.
- [ ] Reorder.
- [ ] Edit traits/role/expertise/instructions.
- [ ] Edit relationships.
- [ ] TTS provider/voice selector placeholder wired to real TTS registry later.
- [ ] Voice preview hook.

**Acceptance criteria**

- User can create 1, 2, 3, 4, 5, and 6-host configurations without schema/UI assumptions about two hosts.

---

# Milestone 10 — Episode planning

## DD-090 — Episode configuration service

- [ ] Create/edit episode.
- [ ] Configure title/focus/audience/depth/duration/style.
- [ ] Select ordered hosts.
- [ ] Configure must-cover/avoid topics.
- [ ] Apply source/research overrides.
- [ ] Snapshot relevant project configuration for generation reproducibility.

**Acceptance criteria**

- Two episodes in same project can use different hosts, models, and research policies without altering each other.

## DD-091 — Structured episode planner

- [ ] Retrieve relevant evidence for focus.
- [ ] Generate structured EpisodePlan.
- [ ] Generate ordered SegmentPlans.
- [ ] Allocate duration/word budgets.
- [ ] Assign suggested lead hosts/evidence.
- [ ] Persist plan.
- [ ] Support regeneration of whole plan.
- [ ] Support targeted segment regeneration.

**Acceptance criteria**

- Plan duration budget is bounded around target duration by explicit policy.
- Invalid structured output is repaired/bounded via DD-055 mechanisms.

## DD-092 — Episode setup TUI

- [ ] Title/focus editor.
- [ ] Audience.
- [ ] Technical depth.
- [ ] Duration.
- [ ] Style.
- [ ] Host selection/order summary.
- [ ] Research/citation behavior controls.
- [ ] Build-plan action.

**Acceptance criteria**

- TUI validates missing hosts/provider roles before planning.

## DD-093 — Episode plan TUI

- [ ] Segment list.
- [ ] Duration estimates.
- [ ] Purpose/questions/evidence/lead hosts.
- [ ] Edit selected segment.
- [ ] Regenerate segment.
- [ ] Regenerate plan.
- [ ] Approve and generate.
- [ ] Explicit auto-generate option.

**Acceptance criteria**

- User can reject/change a plan before any host dialogue/TTS calls occur.

---

# Milestone 11 — Conversation director and multi-host generation

## DD-100 — Conversation state model

- [ ] Persist segment progress.
- [ ] Persist running conversation summary.
- [ ] Persist unresolved questions/topics.
- [ ] Persist recent-turn context references.
- [ ] Persist participation statistics as advisory state.

**Acceptance criteria**

- Conversation can resume after process restart without needing full transcript in memory.

## DD-101 — Director decision schema

- [ ] Define structured next-turn/director decision.
- [ ] Include next speaker.
- [ ] Include intent.
- [ ] Include evidence IDs.
- [ ] Include target duration/length.
- [ ] Include handoff/interaction instruction.
- [ ] Include segment transition/completion signal.

**Acceptance criteria**

- Director cannot name a host not participating in episode.
- Director cannot cite nonexistent evidence IDs.

## DD-102 — Director engine

- [ ] Select speaker based on segment purpose, roles, relationships, prior participation, and evidence.
- [ ] Manage pacing.
- [ ] Manage transitions.
- [ ] Avoid repetitive agreement.
- [ ] Avoid artificial disagreement unsupported by evidence.
- [ ] Manage callbacks/questions.
- [ ] Stop segment/episode within configured bounds.

**Acceptance criteria**

- Deterministic fake-model tests exercise 1-, 2-, 3-, and 5-host episodes.
- No code path assumes alternating A/B speakers.

## DD-103 — Host prompt/context assembly

- [ ] Combine host profile.
- [ ] Include director instruction.
- [ ] Include recent dialogue.
- [ ] Include compact conversation state.
- [ ] Include only relevant evidence, with stable IDs.
- [ ] Include relationship context when relevant.
- [ ] Enforce citation/grounding instructions.

**Acceptance criteria**

- Prompt assembly is unit tested and source evidence includes origin/location metadata.

## DD-104 — Host turn generation

- [ ] Generate one bounded host turn from director decision.
- [ ] Validate speaker identity.
- [ ] Capture citations/evidence IDs.
- [ ] Persist turn before advancing.
- [ ] Update conversation state.
- [ ] Checkpoint per turn.

**Acceptance criteria**

- Forced failure on turn N resumes at N without duplicating turns 1..N-1.

## DD-105 — Duration and pacing controller

- [ ] Estimate spoken duration from text/voice baseline.
- [ ] Track actual generated word budget.
- [ ] Adapt remaining segment budget.
- [ ] Prevent runaway turn count with hard safety bounds.
- [ ] Permit concise early completion when content is exhausted.

**Acceptance criteria**

- Synthetic tests show bounded completion for too-terse and too-verbose fake models.

## DD-106 — Conversation quality heuristics

- [ ] Detect highly repetitive phrase/turn patterns.
- [ ] Detect one host monopolizing unintentionally.
- [ ] Detect excessive shallow acknowledgements.
- [ ] Detect unsupported citation IDs.
- [ ] Permit corrective director step or targeted regeneration.

**Acceptance criteria**

- Heuristics warn/correct deterministic bad fake conversations without requiring manual intervention.

---

# Milestone 12 — Claim extraction and verification

## DD-110 — Material claim extraction

- [ ] Identify material factual claims from generated turns.
- [ ] Exclude obvious greetings/transitions/opinions from mandatory verification.
- [ ] Link claims to turn spans.
- [ ] Persist claim records.

**Acceptance criteria**

- Claim extraction fixture differentiates factual statements from conversational filler.

## DD-111 — Evidence retrieval for claims

- [ ] Retrieve supporting and counterevidence across primary and supplemental sources.
- [ ] Preserve origin distinctions.
- [ ] Include source-location metadata.

**Acceptance criteria**

- Contradictory evidence can coexist with supporting evidence for one claim.

## DD-112 — Verification classifier

- [ ] Implement Supported.
- [ ] Implement Partially Supported.
- [ ] Implement Contradicted.
- [ ] Implement Insufficient Evidence.
- [ ] Implement Not Applicable.
- [ ] Persist rationale/confidence where appropriate.

**Acceptance criteria**

- Structured verification output is schema validated.
- Verification never changes original source content.

## DD-113 — Targeted repair

- [ ] Identify turns requiring repair.
- [ ] Regenerate turn using verification feedback/evidence.
- [ ] Recheck affected claims.
- [ ] Update downstream conversation summary if necessary.
- [ ] Preserve unaffected turn IDs/content when possible.

**Acceptance criteria**

- Repairing one turn does not regenerate the full episode.

## DD-114 — Claim inspector TUI

- [ ] Select claim from turn/transcript.
- [ ] Display verification state.
- [ ] Display supporting/contradicting evidence.
- [ ] Display source origin/location.
- [ ] Open parsed source passage.
- [ ] Regenerate/repair action.

**Acceptance criteria**

- TUI test traces a generated claim to exact fixture source chunk(s).

---

# Milestone 13 — TTS provider subsystem and KittenTTS

## DD-120 — TTS provider contract and registry

- [ ] Define synthesize/voices/health contract.
- [ ] Normalize voice metadata.
- [ ] Normalize audio result metadata.
- [ ] Add deterministic fake TTS provider.
- [ ] Add per-host provider/voice resolution.

**Acceptance criteria**

- One episode can resolve different TTS providers for different hosts.

## DD-121 — KittenTTS Micro runtime integration

- [ ] Integrate KittenTTS Micro behind provider contract.
- [ ] CPU-only operation path.
- [ ] Enumerate bundled/supported voices.
- [ ] Handle model/runtime absence cleanly.
- [ ] Isolate blocking inference from Textual event loop.
- [ ] Ensure cancellation is truthful: no UI claim that an uninterruptible inference was cancelled before it actually stops/returns.

**Acceptance criteria**

- Local opt-in smoke test synthesizes valid audio on CPU.
- Normal CI uses fake/model-free tests.

## DD-122 — KittenTTS model manager

- [ ] On-demand installation/download.
- [ ] Version/installed-state tracking.
- [ ] Download integrity verification where upstream artifacts permit.
- [ ] Partial-download cleanup/recovery.
- [ ] Configurable model directory.
- [ ] Uninstall/reinstall support.

**Acceptance criteria**

- Base package installation does not bundle model weights.
- Interrupted fake download recovers without treating partial file as installed.

## DD-123 — KittenTTS voice preview

- [ ] Deterministic preview sentence.
- [ ] Preview cache by model/voice/settings/text hash.
- [ ] Playback/export mechanism.
- [ ] Clear errors when local audio playback unavailable.

**Acceptance criteria**

- Previewing same unchanged voice can reuse cache.

## DD-124 — KittenTTS benchmark

- [ ] Synthesize deterministic benchmark passage.
- [ ] Measure wall time.
- [ ] Determine generated audio duration.
- [ ] Compute real-time factor and x-realtime.
- [ ] Estimate 20/30-minute render time.
- [ ] Save runtime/model/CPU metadata useful for later display.

**Acceptance criteria**

- Benchmark math is unit tested independently of real model.

## DD-125 — OpenAI TTS adapter

- [ ] Implement supported OpenAI speech API path.
- [ ] Voice/model discovery/config as available.
- [ ] Normalize audio result.
- [ ] Handle rate/auth/timeout errors.

**Acceptance criteria**

- Mock contract tests cover normal/error paths.

## DD-126 — Generic OpenAI-compatible TTS adapter

- [ ] Configurable base URL.
- [ ] Optional credential/header reference.
- [ ] Model.
- [ ] Voice.
- [ ] Response format.
- [ ] Timeout.
- [ ] Graceful handling of compatibility deviations.

**Acceptance criteria**

- Test against a local fake OpenAI-compatible HTTP server fixture.

## DD-127 — ElevenLabs adapter

- [ ] Implement synthesis.
- [ ] Voice discovery.
- [ ] Model/config handling.
- [ ] Normalize audio.
- [ ] Handle auth/rate/timeout failures.

**Acceptance criteria**

- Mock contract tests cover voice listing and synthesis.

## DD-128 — Host TTS UI completion

- [ ] Connect host editor to TTS registry.
- [ ] Provider selector.
- [ ] Voice selector.
- [ ] Preview action.
- [ ] Kitten model-install prompt/action.
- [ ] Local benchmark action.

**Acceptance criteria**

- User can configure a 3-host episode with three Kitten voices and no cloud TTS account.

---

# Milestone 14 — Audio composition and export

## DD-130 — Audio decode/normalization

- [ ] Decode provider formats into canonical PCM representation.
- [ ] Resample to canonical composition rate.
- [ ] Normalize channel layout.
- [ ] Validate corrupt/empty provider output.

**Acceptance criteria**

- Fixture MP3/WAV/provider outputs normalize to expected PCM metadata.

## DD-131 — Audio timeline model

- [ ] Represent ordered turn audio clips.
- [ ] Represent pauses.
- [ ] Represent bounded overlap/interruption.
- [ ] Generate chapter timestamps.
- [ ] Persist timeline metadata.

**Acceptance criteria**

- Timeline duration math is deterministic and tested.

## DD-132 — TTS generation stage

- [ ] Generate TTS per turn.
- [ ] Cache by text+voice+provider/model/settings identity.
- [ ] Persist TTS artifact IDs/status.
- [ ] Checkpoint each completed turn.
- [ ] Bounded concurrency where safe.

**Acceptance criteria**

- Failure on TTS turn N resumes without re-synthesizing valid cached turns.

## DD-133 — FFmpeg integration

- [ ] Detect/configure FFmpeg.
- [ ] Invoke without shell interpolation.
- [ ] Compose canonical timeline.
- [ ] Apply loudness normalization strategy.
- [ ] Capture sanitized stderr on failure.

**Acceptance criteria**

- Paths containing spaces/shell metacharacters do not cause command injection or malformed invocation.

## DD-134 — Export artifacts

- [ ] WAV export.
- [ ] MP3 export.
- [ ] Markdown transcript.
- [ ] Source manifest Markdown or JSON.
- [ ] Episode metadata JSON.
- [ ] Stable output naming with collision handling.

**Acceptance criteria**

- Exported manifest distinguishes primary vs supplemental sources.
- Exported metadata excludes secrets.

## DD-135 — Partial audio regeneration

- [ ] Invalidate TTS only for changed turns/voices/settings.
- [ ] Recompose final audio from cached unaffected clips.
- [ ] Update timestamps/chapters after text-duration changes.

**Acceptance criteria**

- Changing one turn demonstrably does not call TTS for unrelated unchanged turns.

---

# Milestone 15 — End-to-end generation orchestration

## DD-140 — Pipeline stage orchestrator

- [ ] Implement ordered durable stage state machine from spec.
- [ ] Support stage skip when valid artifact exists.
- [ ] Support forced rebuild of selected downstream stage.
- [ ] Emit structured progress events.
- [ ] Bound concurrency and retries.

**Acceptance criteria**

- Full fake-provider pipeline produces a completed episode.
- Re-running completed episode does not duplicate durable artifacts.

## DD-141 — Pause/resume/cancel

- [ ] Cooperative pause.
- [ ] Cooperative cancel.
- [ ] Resume after process restart.
- [ ] Clear status for operations that cannot be interrupted mid-call.
- [ ] Preserve completed units.

**Acceptance criteria**

- Automated integration tests pause/resume during conversation and TTS stages.

## DD-142 — Failure injection/resumption matrix

- [ ] Add test hooks to fail after source parse.
- [ ] Fail during research.
- [ ] Fail during planning.
- [ ] Fail at arbitrary conversation turn.
- [ ] Fail during verification.
- [ ] Fail at arbitrary TTS turn.
- [ ] Fail during composition/export.
- [ ] Verify restart/resume semantics for each.

**Acceptance criteria**

- No tested failure path loses already committed work or creates duplicate turns/audio artifacts.

## DD-143 — Preflight service

- [ ] Resolve providers/models for all required roles.
- [ ] Test required provider health.
- [ ] Check TTS voices/model availability.
- [ ] Check FFmpeg.
- [ ] Check source availability/index state.
- [ ] Estimate transcript/episode size.
- [ ] Add cloud-cost estimate only where pricing data is explicitly available/configured and label it as estimate.

**Acceptance criteria**

- Generation cannot begin with a known hard preflight blocker unless user invokes an explicitly supported override for a nonfatal warning.

---

# Milestone 16 — Full generation/review TUI

## DD-150 — Preflight TUI screen

- [ ] Source counts.
- [ ] Host count.
- [ ] expected duration.
- [ ] LLM role assignments/health.
- [ ] TTS host assignments/health.
- [ ] FFmpeg state.
- [ ] warnings/blockers.
- [ ] Generate/Cancel.

**Acceptance criteria**

- Fake unhealthy provider produces actionable blocker text.

## DD-151 — Generation monitor

- [ ] Stage checklist.
- [ ] Current section/turn.
- [ ] Recent generated turns.
- [ ] TTS progress.
- [ ] Research progress.
- [ ] Progress values only when meaningful.
- [ ] Pause/resume/cancel.
- [ ] View transcript.
- [ ] View diagnostic errors/log summary.

**Acceptance criteria**

- TUI remains responsive while fake long-running providers execute asynchronously.

## DD-152 — Episode library TUI

- [ ] List complete/draft/failed/paused episodes.
- [ ] Open/review.
- [ ] Resume.
- [ ] Duplicate configuration.
- [ ] Export.
- [ ] Delete with confirmation.
- [ ] New episode action.

**Acceptance criteria**

- Project with multiple episodes accurately preserves independent run states.

## DD-153 — Transcript/review TUI

- [ ] Chapter list.
- [ ] Transcript grouped by turn/host.
- [ ] Source citations/evidence for selected turn.
- [ ] Claims pane.
- [ ] Regenerate turn/section action.
- [ ] Export action.

**Acceptance criteria**

- Selected turn can navigate to source passage/claim inspector.

## DD-154 — Audio playback integration

- [ ] Determine portable terminal/local-player strategy.
- [ ] Play/pause where supported.
- [ ] Seek/skip where supported or provide documented reduced capability.
- [ ] Keep selected chapter/turn synchronized approximately when feasible.
- [ ] Fail gracefully on headless systems with no playback backend.

**Acceptance criteria**

- Lack of an audio device/player does not prevent episode generation/export.

## DD-155 — Quick Deep Dive

- [ ] Add Quick Deep Dive action.
- [ ] Use configured defaults.
- [ ] Default host pair: Curious Explainer + Skeptic unless user defaults override.
- [ ] Default target ~20 minutes.
- [ ] Default Useful research policy unless configured otherwise.
- [ ] Still create normal durable plan/run/artifacts.

**Acceptance criteria**

- From an indexed project, quick flow reaches preflight/generation without visiting every advanced screen.

---

# Milestone 17 — CLI feature parity for automation

## DD-160 — Source CLI

- [ ] `source add` file.
- [ ] `source add` directory.
- [ ] URL input.
- [ ] list/show/include/exclude/remove.
- [ ] JSON output where useful.

## DD-161 — Research CLI

- [ ] analyze gaps.
- [ ] list gaps.
- [ ] research selected/all.
- [ ] ignore gap.
- [ ] list supplemental sources/candidate outcomes.

## DD-162 — Host CLI

- [ ] list presets.
- [ ] create host from preset.
- [ ] edit primary host fields.
- [ ] list project hosts.
- [ ] assign voice/provider.

## DD-163 — Episode CLI

- [ ] create/configure episode.
- [ ] plan.
- [ ] show plan.
- [ ] generate.
- [ ] pause/cancel if addressed by process/job control model.
- [ ] resume.
- [ ] status.
- [ ] export.

## DD-164 — Provider CLI

- [ ] list.
- [ ] health/test.
- [ ] model discovery.
- [ ] voice discovery.
- [ ] Kitten install/status/benchmark.

**Milestone acceptance criteria**

- A scripted fake-provider end-to-end workflow can create a project, add sources, configure hosts, plan, generate, and export without launching Textual.

---

# Milestone 18 — Privacy, diagnostics, and hardening

## DD-170 — Content-routing transparency

- [ ] Preflight indicates which stages send content to which providers.
- [ ] Distinguish local vs remote provider routes.
- [ ] Warn when private user source text will be sent to a configured cloud provider.
- [ ] Add project local-only enforcement mode if feasible now; otherwise add explicit follow-up task/spec entry before V1 release.

**Acceptance criteria**

- User can determine before generation whether source text will leave the machine.

## DD-171 — Log redaction and diagnostic bundle

- [ ] Centralized structured logging.
- [ ] Secret redaction.
- [ ] Run IDs.
- [ ] Sanitized provider diagnostics.
- [ ] Diagnostic export excluding source contents by default.
- [ ] Explicit opt-in if source excerpts are ever included.

**Acceptance criteria**

- Tests inject recognizable secrets into headers/config and verify they never appear in exported diagnostics.

## DD-172 — Network hardening audit

- [ ] Re-audit automated research SSRF controls.
- [ ] Re-audit redirects/DNS rebinding assumptions.
- [ ] Re-audit download limits/timeouts.
- [ ] Re-audit user-explicit URL behavior and document it.

**Acceptance criteria**

- Security-focused tests cover IPv4/IPv6 private/link-local/loopback cases and redirect chains.

## DD-173 — Filesystem/process hardening audit

- [ ] Re-audit project path isolation.
- [ ] Re-audit archive/document parser temporary files.
- [ ] Re-audit FFmpeg/player subprocess argument handling.
- [ ] Re-audit permissions for secret/config files where platform allows.

**Acceptance criteria**

- No shell=True or equivalent unsafe interpolation in external-process paths without an explicitly reviewed justification.

## DD-174 — Cache/invalidation audit

- [ ] Source changes invalidate appropriate chunks/indexes/plans.
- [ ] Host text changes invalidate relevant conversation/TTS.
- [ ] Voice changes invalidate relevant TTS/audio only.
- [ ] Provider/model changes invalidate relevant generated artifacts.
- [ ] App upgrades/migrations do not silently reuse incompatible cache formats.

**Acceptance criteria**

- Automated invalidation matrix covers common edits and proves minimal necessary recomputation.

---

# Milestone 19 — UX polish and accessibility

## DD-180 — Terminal-size and responsive-layout pass

- [ ] Validate 80x24 minimum workflow.
- [ ] Improve large-terminal multi-pane layouts.
- [ ] Prevent clipped critical actions.
- [ ] Add scroll behavior where needed.

## DD-181 — Keyboard/command palette completeness

- [ ] Every primary workflow action has keyboard access.
- [ ] Shortcuts are discoverable.
- [ ] Command palette exposes common navigation/actions.
- [ ] Avoid conflicting shortcuts across screens.

## DD-182 — Non-color status semantics

- [ ] Add textual/icons/symbol status independent of color.
- [ ] Audit errors/warnings/progress/provider-health indicators.

## DD-183 — Error-message UX pass

- [ ] Convert common parser/provider/network/TTS/FFmpeg failures into actionable user messages.
- [ ] Preserve detailed diagnostics behind a secondary action.
- [ ] Avoid leaking secrets/internal raw tracebacks by default.

## DD-184 — First-run experience

- [ ] Welcome/setup flow.
- [ ] Detect FFmpeg.
- [ ] Offer KittenTTS Micro installation.
- [ ] Offer provider setup.
- [ ] Permit local providers only.
- [ ] Permit skipping cloud configuration.
- [ ] Provide sample/empty project guidance without bundling copyrighted content.

**Milestone acceptance criteria**

- A clean-user usability smoke test can reach a generated local/fake episode without editing config files manually.

---

# Milestone 20 — Documentation

## DD-190 — README

- [ ] Product overview.
- [ ] Screenshots or terminal captures when UI stabilizes.
- [ ] Prerequisites.
- [ ] Install with uv.
- [ ] First-run flow.
- [ ] Local-only example.
- [ ] Cloud-provider example.
- [ ] Project/source/episode concepts.
- [ ] Link to full spec.

## DD-191 — Provider documentation

- [ ] OpenAI LLM setup.
- [ ] Ollama setup.
- [ ] llama-server setup.
- [ ] KittenTTS setup.
- [ ] OpenAI TTS setup.
- [ ] OpenAI-compatible TTS setup.
- [ ] ElevenLabs setup.
- [ ] Credential storage behavior.

## DD-192 — Research/provenance documentation

- [ ] Explain primary vs supplemental sources.
- [ ] Explain research modes.
- [ ] Explain research-gap workflow.
- [ ] Explain source-quality limitations.
- [ ] Explain citation/claim verification limits.

## DD-193 — Architecture/developer documentation

- [ ] Layering/dependency direction.
- [ ] Domain model.
- [ ] Provider contracts.
- [ ] Persistence/migrations.
- [ ] checkpointing/resume.
- [ ] adding a new LLM provider.
- [ ] adding a new TTS provider.
- [ ] adding a parser.
- [ ] testing with fake providers.

## DD-194 — Privacy/security documentation

- [ ] What data can leave the machine.
- [ ] How provider routing works.
- [ ] Secret handling.
- [ ] Supplemental web research behavior.
- [ ] Local-only configuration.
- [ ] Diagnostic export contents.

---

# Milestone 21 — V1 integration qualification

## DD-200 — Deterministic end-to-end fixture project

- [ ] Create small synthetic/public-domain fixture corpus.
- [ ] Fake research provider returns supplemental fixture evidence.
- [ ] Fake LLM drives 3-host conversation.
- [ ] Fake TTS produces deterministic audio clips.
- [ ] Pipeline exports transcript/source manifest/metadata/audio.

**Acceptance criteria**

- Entire fixture generation runs in ordinary CI.
- No network access is required.

## DD-201 — Multi-host matrix

Qualify at least:

- [ ] one host;
- [ ] two hosts;
- [ ] three hosts;
- [ ] five hosts;
- [ ] mixed host roles;
- [ ] host relationships;
- [ ] mixed TTS providers using fakes.

**Acceptance criteria**

- No host-count-specific crash or A/B alternation assumption.

## DD-202 — Provider matrix

With mock/contract tests and optional real smoke tests, qualify:

- [ ] OpenAI LLM;
- [ ] Ollama;
- [ ] llama-server;
- [ ] KittenTTS Micro;
- [ ] OpenAI TTS;
- [ ] OpenAI-compatible TTS;
- [ ] ElevenLabs.

## DD-203 — Source matrix

Qualify:

- [ ] PDF;
- [ ] DOCX;
- [ ] TXT;
- [ ] Markdown;
- [ ] HTML;
- [ ] explicit URL;
- [ ] pasted text;
- [ ] directory batch import;
- [ ] duplicate handling;
- [ ] excluded source handling.

## DD-204 — Research matrix

Qualify:

- [ ] Off performs no search;
- [ ] Conservative gap path;
- [ ] Useful gap path;
- [ ] Aggressive gap path;
- [ ] newer evidence;
- [ ] contradictory evidence;
- [ ] missing citation;
- [ ] duplicate supplemental candidate;
- [ ] rejected weak/unrelated candidate;
- [ ] supplemental provenance in final manifest.

## DD-205 — Resume/failure matrix

Qualify restart after failure during:

- [ ] parsing/indexing;
- [ ] research;
- [ ] planning;
- [ ] turn generation;
- [ ] verification;
- [ ] TTS;
- [ ] composition;
- [ ] export.

## DD-206 — Privacy/security matrix

Qualify:

- [ ] secret redaction;
- [ ] provider routing transparency;
- [ ] automated research SSRF protections;
- [ ] path traversal protection;
- [ ] safe subprocess invocation;
- [ ] diagnostic bundle privacy defaults.

## DD-207 — Fresh-machine installation test

- [ ] Install from documented instructions in a clean environment.
- [ ] Launch TUI.
- [ ] Create project/import corpus.
- [ ] Configure at least one local or fake/dev LLM path.
- [ ] Install/use KittenTTS Micro in a real CPU smoke environment.
- [ ] Generate/export a small episode.
- [ ] Record any undocumented prerequisite and fix docs/installer.

## DD-208 — Exact-head V1 CI gate

- [ ] Ruff passes.
- [ ] Static typing passes.
- [ ] Unit tests pass.
- [ ] Integration tests pass.
- [ ] TUI tests pass.
- [ ] Deterministic end-to-end test passes.
- [ ] Package build/install smoke passes.
- [ ] Lockfile is current.
- [ ] No required live credentials in CI.
- [ ] Spec and TODO accurately reflect implemented state.

**Milestone acceptance criteria**

All V1 criteria in `docs/DEEP_DIVE_TUI_SPEC.md` section “V1 definition of done” are demonstrably satisfied at the exact default-branch head.

---

# Post-V1 candidates — do not block V1 unless promoted

These are intentionally not V1 commitments. Promote them into numbered implementation tasks only after a deliberate decision.

- [ ] EPUB ingestion.
- [ ] YouTube/public transcript helper.
- [ ] Additional embedding backends.
- [ ] Dedicated neural reranker.
- [ ] Kokoro local TTS option.
- [ ] Piper external/local TTS integration.
- [ ] Additional conversation styles: Expert Roundtable, Debate, Teaching Session, Journal Club.
- [ ] Listener can interrupt/join the conversation interactively.
- [ ] Address a question to a specific host and dynamically replan.
- [ ] Voice cloning where legally/ethically appropriate and explicitly enabled.
- [ ] Optional intro/outro music and production templates.
- [ ] Podcast RSS/publication support.
- [ ] Web/API frontend using the existing application layer.
- [ ] Remote worker/execution backend.
- [ ] Multi-user collaboration.
- [ ] Project import/export archive.
- [ ] Advanced evidence graph visualization.
- [ ] Cross-project source library.
- [ ] Additional languages/localization.
- [ ] Automatic speaker-style adaptation based on target language.
- [ ] Optional source watch/refresh for ongoing projects.

---

# Final completion checklist

Do not declare the implementation complete until all of the following are true:

- [ ] Every V1 task above is checked complete or explicitly removed/deferred through an accompanying spec/TODO revision.
- [ ] The TUI happy path works from project creation through episode export.
- [ ] The CLI can run the core workflow headlessly.
- [ ] User documents remain distinguishable from supplemental research everywhere.
- [ ] OpenAI, Ollama, and llama-server LLM adapters are implemented and contract-tested.
- [ ] KittenTTS Micro is usable as the built-in local CPU TTS.
- [ ] OpenAI TTS, OpenAI-compatible TTS, and ElevenLabs adapters are implemented and contract-tested.
- [ ] Two-or-more-host operation is native; no fixed two-host architecture remains.
- [ ] Host presets and fully custom host profiles work.
- [ ] Supplemental research is gap-driven and inspectable.
- [ ] Claim/evidence inspection works.
- [ ] Long generation is checkpointed and resumable.
- [ ] Targeted turn/TTS regeneration does not discard unaffected work.
- [ ] Exported audio, transcript, source manifest, and metadata are valid.
- [ ] Secrets are not persisted or exported accidentally.
- [ ] Automated research has network safety controls.
- [ ] Fresh-machine documentation is verified.
- [ ] Exact-head CI is green.
- [ ] `docs/DEEP_DIVE_TUI_SPEC.md` and this TODO describe the product that actually exists.
