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

# Milestone 2 — Persistence and workspace

<!-- Earlier completed milestones unchanged. -->

# Milestone 16 — Full generation/review TUI

## DD-150 — Preflight TUI screen

- [x] Source counts.
- [x] Host count.
- [x] expected duration.
- [x] LLM role assignments/health.
- [x] TTS host assignments/health.
- [x] FFmpeg state.
- [x] warnings/blockers.
- [x] Generate/Cancel.

**Acceptance criteria**

- Fake unhealthy provider produces actionable blocker text.

## DD-151 — Generation monitor

- [x] Stage checklist.
- [x] Current section/turn.
- [x] Recent generated turns.
- [x] TTS progress.
- [x] Research progress.
- [x] Progress values only when meaningful.
- [x] Pause/resume/cancel.
- [x] View transcript.
- [x] View diagnostic errors/log summary.

**Acceptance criteria**

- TUI remains responsive while fake long-running providers execute asynchronously.

## DD-152 — Episode library TUI

- [x] List complete/draft/failed/paused episodes.
- [x] Open/review.
- [x] Resume.
- [x] Duplicate configuration.
- [x] Export.
- [x] Delete with confirmation.
- [x] New episode action.

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
