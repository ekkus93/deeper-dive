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

- [x] Chapter list.
- [x] Transcript grouped by turn/host.
- [x] Source citations/evidence for selected turn.
- [x] Claims pane.
- [x] Regenerate turn/section action.
- [x] Export action.

**Acceptance criteria**

- Selected turn can navigate to source passage/claim inspector.

## DD-154 — Audio playback integration

- [x] Determine portable terminal/local-player strategy.
- [x] Play/pause where supported.
- [x] Seek/skip where supported or provide documented reduced capability.
- [x] Keep selected chapter/turn synchronized approximately when feasible.
- [x] Fail gracefully on headless systems with no playback backend.

**Acceptance criteria**

- Lack of an audio device/player does not prevent episode generation/export.

## DD-155 — Quick Deep Dive

- [x] Add Quick Deep Dive action.
- [x] Use configured defaults.
- [x] Default host pair: Curious Explainer + Skeptic unless user defaults override.
- [x] Default target ~20 minutes.
- [x] Default Useful research policy unless configured otherwise.
- [x] Still create normal durable plan/run/artifacts.

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
