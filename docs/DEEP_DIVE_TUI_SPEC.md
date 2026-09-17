# Deeper Dive — Product, Architecture, and UX Specification

**Status:** Initial design authority  
**Repository:** `ekkus93/deeper-dive`  
**Primary implementation language:** Python 3.12+  
**Primary interface:** Textual TUI  

## 1. Purpose

Deeper Dive is a local-first, source-grounded application for generating long-form, multi-host audio conversations from a user-supplied document corpus.

The product is inspired by the useful interaction pattern of AI-generated source-grounded audio discussions, but it is intentionally more configurable and inspectable. In particular, Deeper Dive must support:

- two or more hosts rather than a fixed two-host format;
- configurable host personalities, epistemic roles, expertise, relationships, and voices;
- user-supplied documents as the primary evidence corpus;
- optional supplemental web research when outside sources would materially improve the discussion;
- explicit provenance distinguishing user-supplied sources from supplemental sources;
- provider-agnostic LLM use with OpenAI, Ollama, and llama-server;
- provider-agnostic TTS with built-in KittenTTS Micro plus OpenAI TTS, OpenAI-compatible TTS services, and ElevenLabs;
- checkpointed, resumable generation;
- transcript, citation, source, and claim inspection;
- a polished terminal UI suitable for local Linux use, SSH, and headless machines;
- a noninteractive CLI using the same application/service layer as the TUI.

Deeper Dive is not intended to imitate a proprietary product's implementation. It should implement the product behavior described in this specification using its own architecture and code.

---

## 2. Product principles

### 2.1 Primary sources are primary

Documents supplied by the user are the authoritative starting corpus for each project. Supplemental research must never silently become indistinguishable from user-supplied material.

Every evidence item used to generate or verify a statement must retain provenance sufficient to answer:

- Which source did this come from?
- Was that source supplied by the user or discovered by the application?
- Where in the source does the supporting evidence appear?
- When and why was a supplemental source added?
- Which generated claims depend on it?

### 2.2 Supplemental research must be purposeful

The application must not issue broad, arbitrary web searches merely because research is enabled. It should first analyze the corpus and identify explicit research gaps, such as:

- important material is outdated;
- key cited works are missing;
- supplied sources disagree;
- a claim would benefit from corroboration;
- later replications or reviews could materially change the interpretation;
- background context is required for the intended audience;
- a current development is relevant to the requested episode.

Each supplemental search should record the gap or research question that motivated it.

### 2.3 Personalities shape behavior, not truth

A host configured as a skeptic should probe assumptions, seek counterevidence, and surface limitations. It must not be instructed to disagree regardless of evidence.

A host configured as an enthusiast should not exaggerate evidence. A historian should not invent chronology. A domain expert should not claim unsupported expertise-dependent facts.

Host personalities control interaction style and evidence priorities, not factual outcomes.

### 2.4 Generation should be inspectable

The user should be able to inspect intermediate artifacts:

- parsed sources;
- research gaps;
- supplemental candidates and reasons for acceptance/rejection;
- evidence map;
- episode outline;
- generated turns;
- claim verification results;
- citations;
- TTS artifacts;
- final audio.

The normal workflow should remain simple, but advanced users must be able to understand why the application produced a result.

### 2.5 Long jobs must be durable

Generation may involve many LLM calls, web requests, and TTS operations. The application must checkpoint durable progress. A process crash, terminal disconnect, provider error, or manual quit must not require restarting a completed stage or regenerating already completed turns unless the user explicitly requests it.

### 2.6 The UI is a client of the engine

The Textual TUI must not directly call LLM or TTS providers. All application logic lives in provider, service, orchestration, and persistence layers that are usable from both the TUI and CLI.

---

## 3. Initial technical stack

The preferred initial stack is:

- Python 3.12+
- `uv` for environments, dependency locking, and developer commands
- Textual for the terminal UI
- Pydantic v2 for configuration and domain validation
- `httpx` for asynchronous HTTP
- `asyncio` for orchestration
- SQLite for durable project metadata and job/checkpoint state
- a migration mechanism suitable for SQLite schema evolution
- FFmpeg as the external audio compositor/encoder dependency
- pytest for automated testing
- Ruff for formatting/linting
- mypy or Pyright for static type checking, selected during project bootstrap

Dependency choices may be refined during implementation when concrete technical constraints are discovered, but changes to major architectural choices should be reflected in this specification.

---

## 4. High-level architecture

```text
                         ┌──────────────────────────┐
                         │       Textual TUI        │
                         └────────────┬─────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │      Application API     │
                         │ projects / jobs / events │
                         └────────────┬─────────────┘
                                      │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
┌───────▼────────┐          ┌────────▼─────────┐          ┌────────▼─────────┐
│ Source/Research│          │ Conversation     │          │ Audio/TTS        │
│ Services       │          │ Services         │          │ Services         │
└───────┬────────┘          └────────┬─────────┘          └────────┬─────────┘
        │                             │                             │
        └──────────────┬──────────────┴──────────────┬──────────────┘
                       │                             │
              ┌────────▼─────────┐          ┌────────▼─────────┐
              │ Provider Layer   │          │ Persistence      │
              │ LLM/TTS/Search   │          │ SQLite + files   │
              └──────────────────┘          └──────────────────┘
```

The package layout should follow this separation. A suggested starting layout is:

```text
src/deeper_dive/
├── app/
│   ├── service.py
│   ├── events.py
│   ├── commands.py
│   ├── cli/
│   └── tui/
│       ├── app.py
│       ├── screens/
│       └── widgets/
├── core/
│   ├── models.py
│   ├── config.py
│   ├── errors.py
│   └── ids.py
├── storage/
│   ├── database.py
│   ├── migrations/
│   ├── repositories.py
│   └── workspace.py
├── sources/
│   ├── ingest.py
│   ├── parsers/
│   ├── chunking.py
│   └── metadata.py
├── retrieval/
│   ├── index.py
│   ├── lexical.py
│   ├── vectors.py
│   ├── rerank.py
│   └── embeddings/
├── research/
│   ├── planner.py
│   ├── search.py
│   ├── fetch.py
│   ├── quality.py
│   └── evidence.py
├── llm/
│   ├── base.py
│   ├── capabilities.py
│   ├── openai.py
│   ├── ollama.py
│   └── llama_server.py
├── conversation/
│   ├── hosts.py
│   ├── presets.py
│   ├── planning.py
│   ├── director.py
│   ├── turns.py
│   ├── verification.py
│   └── transcript.py
├── tts/
│   ├── base.py
│   ├── kitten.py
│   ├── openai.py
│   ├── openai_compatible.py
│   └── elevenlabs.py
└── audio/
    ├── normalize.py
    ├── timeline.py
    ├── compositor.py
    └── export.py
```

Exact filenames are not contractual. Layer boundaries are.

---

## 5. Project and workspace model

A **project** is a persistent research workspace containing sources, research results, host definitions, configuration, and zero or more episodes.

An **episode** is one generated conversation derived from a project. A project may produce many episodes without reimporting its corpus.

Suggested on-disk layout:

```text
~/.local/share/deeper-dive/
├── models/
│   └── tts/
└── projects/
    └── <project-id>/
        ├── project.db
        ├── sources/
        ├── supplemental/
        ├── cache/
        ├── indexes/
        ├── runs/
        ├── transcripts/
        └── output/
```

The base data directory must follow platform conventions and be configurable.

Project data should use stable generated IDs internally rather than user-editable names as primary keys.

---

## 6. Core domain model

The implementation should formalize at least the following concepts.

### 6.1 Project

Representative fields:

- stable ID;
- display name;
- created/modified timestamps;
- project-level instructions;
- default research policy;
- default provider/model role assignments;
- active corpus/index version;
- current schema version.

### 6.2 Source

Representative fields:

- stable ID;
- source origin: `user`, `supplemental`, or `generated_reference` if later needed;
- source type: PDF, DOCX, text, Markdown, HTML, URL, transcript, etc.;
- original filename or URL;
- normalized title;
- authors/publisher/date when available;
- content hash;
- import timestamp;
- retrieval timestamp for remote sources;
- inclusion/exclusion state;
- quality/relevance metadata;
- research-gap ID that motivated a supplemental source;
- license/copyright metadata when known;
- parsing status and errors.

### 6.3 SourceChunk

Representative fields:

- stable ID;
- source ID;
- normalized text;
- ordinal;
- page/section/heading/location metadata;
- start/end offsets where meaningful;
- content hash;
- embedding/index state.

### 6.4 ResearchGap

Representative fields:

- stable ID;
- description;
- rationale;
- gap category;
- priority;
- status: proposed, accepted, ignored, researched, unresolved;
- search queries attempted;
- associated supplemental sources.

### 6.5 Claim and Evidence

A generated or extracted claim should be representable independently from the conversational turn that contains it.

Evidence links should associate a claim with one or more source chunks and include:

- support type: supports, contradicts, contextualizes, uncertain;
- source origin;
- retrieval score(s);
- optional verification confidence;
- human-readable rationale generated during verification where appropriate.

### 6.6 HostProfile

Representative fields:

- stable ID;
- display name;
- optional preset origin;
- role;
- expertise description;
- free-form behavioral instructions;
- trait values such as curiosity, assertiveness, humor, technicality, skepticism, verbosity;
- evidence priorities;
- question frequency;
- analogy preference;
- typical turn length;
- interruption tendency;
- TTS provider and voice configuration;
- relationships to other hosts.

### 6.7 Episode

Representative fields:

- stable ID;
- project ID;
- title;
- focus/instructions;
- intended audience;
- technical depth;
- target duration;
- format/style;
- participating hosts and order;
- source snapshot/corpus version;
- provider/model snapshot;
- state;
- generation run history;
- final artifacts.

### 6.8 EpisodePlan and SegmentPlan

The plan must be a durable artifact, not an ephemeral prompt response.

Each segment should contain:

- title/purpose;
- target duration or word budget;
- key questions;
- required evidence/topics;
- suggested leading host(s);
- expected transitions;
- warnings or disputed points;
- source/evidence references.

### 6.9 ConversationTurn

Representative fields:

- stable ID;
- episode ID;
- segment ID;
- sequence number;
- speaker/host ID;
- director instruction;
- generated text;
- citations/evidence references;
- generation model/provider;
- prompt/template version;
- verification status;
- TTS status and artifact IDs.

### 6.10 GenerationRun / Checkpoint

Each long-running pipeline invocation needs durable state including:

- run ID;
- episode ID;
- current stage;
- stage status;
- completed units;
- failed unit and error;
- retry count;
- provider request metadata sufficient for diagnosis without storing secrets;
- timestamps;
- cancellation/pause state.

---

## 7. Source ingestion

### 7.1 Required initial inputs

V1 should support at minimum:

- PDF;
- DOCX;
- plain text;
- Markdown;
- HTML files;
- HTTP/HTTPS URLs;
- pasted text.

EPUB and transcript-specific helpers are desirable but may land after the minimum ingestion pipeline if they complicate the initial milestone.

### 7.2 Import workflow

Users must be able to:

- add one or more files;
- add a directory recursively;
- add a URL;
- paste text;
- include/exclude an imported source without deleting it;
- delete a source;
- inspect parsed text and metadata;
- see parser/indexing failures.

### 7.3 Deduplication

Use content hashing and canonical remote URLs where possible to prevent accidental duplicate ingestion. Duplicate detection should be transparent and overridable.

### 7.4 Parsing expectations

Parsing should preserve useful structural metadata such as headings and PDF page numbers whenever the parser can recover them reliably.

The application must not pretend that extracted PDF page locations are exact if the parser cannot establish them.

### 7.5 Re-indexing

Changes to inclusion state, parser output, chunking configuration, or embedding configuration must invalidate only the required downstream artifacts. The system should avoid rebuilding unrelated stages.

---

## 8. Retrieval and evidence layer

### 8.1 Retrieval strategy

The initial design should support hybrid retrieval:

```text
query
 ├─ lexical/BM25 search
 └─ vector similarity search
          ↓
       fusion
          ↓
      reranking
          ↓
   evidence chunks
```

A pure lexical path must remain available so a user can run the application without configuring an embedding provider.

### 8.2 Embeddings

Embedding support should be provider-abstracted. The exact initial set may be staged after the LLM/TTS minimum, but the architecture should allow:

- OpenAI embeddings;
- Ollama or compatible local embeddings where available;
- a local sentence-transformer style backend.

### 8.3 Provenance

Retrieved chunks passed into prompts must include stable evidence IDs rather than relying solely on raw source text. Generated outputs that cite evidence must return those IDs in structured form.

### 8.4 Reranking

Reranking may initially be heuristic or LLM-assisted. It must be isolated behind an interface so a dedicated reranker can be introduced later.

---

## 9. Supplemental web research

### 9.1 Research policy

Each project/episode should support four modes:

- **Off** — use only user-supplied sources.
- **Conservative** — search only to fill clear factual/contextual gaps.
- **Useful** — default; search when outside evidence is likely to improve context, verification, recency, or competing perspectives.
- **Aggressive** — actively seek corroboration, disagreement, later research, reviews, missing foundational work, and useful cross-domain context.

### 9.2 Research controls

The UI should expose independent controls such as:

- find newer research;
- look for contradictory evidence;
- find important missing citations;
- prefer primary sources;
- find replication/review evidence;
- add background/context;
- permit general-interest sources.

### 9.3 Gap-first operation

Before searching, the research planner should produce structured `ResearchGap` objects.

A supplemental source must record which gap(s) caused it to be considered.

### 9.4 Search provider abstraction

Web search/fetching must be abstracted from the research planner. Search providers may evolve independently.

The first implementation may use one supported public search mechanism, but the application architecture must not couple research planning directly to a specific commercial search API.

### 9.5 Candidate source evaluation

Candidate sources should be evaluated for:

- relevance;
- duplication;
- recency when recency matters;
- authority/source quality;
- primary-vs-secondary status;
- relationship to the research gap;
- accessibility and extractability.

The ranking policy must be domain-sensitive. For example, official software documentation may be more authoritative than an academic paper for a library API question.

### 9.6 Supplemental provenance

The UI and exports must distinguish supplemental sources from user-supplied sources.

A source manifest should support states such as:

- used substantially;
- background only;
- contradictory/counterevidence;
- discovered by research agent;
- excluded/rejected.

### 9.7 Network safety

Automated research must follow HTTP/HTTPS redirects safely, enforce timeouts and size limits, and protect against unintended access to private/link-local network resources. Explicit user-added local URLs may be governed by a separate user-controlled policy.

---

## 10. LLM provider system

### 10.1 Required providers

V1 must support:

- OpenAI API;
- Ollama;
- llama-server.

Ollama and llama-server should have native adapters even where they provide OpenAI-compatible endpoints. Native adapters allow capability discovery and backend-specific behavior to be handled correctly.

### 10.2 Provider contract

A conceptual provider interface should support:

```python
class LLMProvider(Protocol):
    async def generate(self, request: LLMRequest) -> LLMResponse: ...
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMChunk]: ...
    async def models(self) -> list[ModelInfo]: ...
    async def health(self) -> ProviderHealth: ...
```

Structured output support, tool support, streaming, reasoning controls, context size, and other capabilities should be represented explicitly rather than assumed.

### 10.3 Model roles

Do not require every pipeline stage to use one model. The application should allow independent assignments for roles such as:

- corpus analysis;
- research planning;
- supplemental source analysis;
- evidence extraction;
- episode planning;
- conversation directing;
- host turn generation;
- claim verification.

Project defaults may be overridden per episode.

### 10.4 Request observability

Record useful request diagnostics such as provider, model, latency, token counts if available, retries, and errors. Never persist API keys or authorization headers in logs or project files.

### 10.5 Structured responses

Critical orchestration stages should use validated structured model outputs wherever practical. Invalid output must trigger bounded repair/retry behavior rather than corrupting project state.

---

## 11. Host system

### 11.1 Host count

The engine must represent hosts as `list[HostProfile]`, not fixed `host_a`/`host_b` fields.

Support at minimum:

- one-host narration;
- two-host Deep Dive style conversation;
- three-to-six-host panels/roundtables.

The UI may warn that very large panels can reduce listening clarity, but the core architecture must not hard-code two speakers.

### 11.2 Default presets

Initial host presets should include:

- Curious Explainer;
- Skeptic;
- Synthesizer;
- Domain Expert;
- Practitioner;
- Historian;
- Moderator;
- Custom.

Presets are editable starting points, not immutable classes.

### 11.3 Personality dimensions

The implementation should support both free-form instructions and normalized dimensions such as:

- curiosity;
- assertiveness;
- humor;
- technicality;
- skepticism;
- verbosity;
- question frequency;
- analogy use;
- typical turn length;
- interruption tendency.

### 11.4 Epistemic roles

Roles influence evidence behavior. Examples:

- Explainer favors clarity and primary corpus explanations.
- Skeptic looks for caveats, counterevidence, methodological limitations, and contradictions.
- Synthesizer looks for cross-source and cross-domain connections.
- Domain Expert emphasizes mechanisms and technical precision.
- Practitioner emphasizes practical implications.
- Historian emphasizes chronology and documented intellectual context.
- Moderator manages turn-taking and transitions.

### 11.5 Relationships

Host-to-host relationship instructions should be representable, for example:

```yaml
relationships:
  maya:
    daniel: "asks him to sanity-check technical simplifications"
  daniel:
    priya: "invites her to reconcile apparently conflicting evidence"
```

These relationships should guide interaction without requiring scripted dialogue.

---

## 12. Episode planning

### 12.1 Episode inputs

Episode configuration should include:

- title or auto-title option;
- focus/instructions;
- target audience;
- technical depth;
- target duration;
- style/format;
- participating hosts;
- optional must-cover topics;
- optional avoid topics;
- source inclusion overrides;
- research policy override.

### 12.2 Initial styles

V1 requires a Deep Dive style. The data model should permit later styles such as:

- Expert Roundtable;
- Debate;
- Teaching Session;
- Journal Club.

### 12.3 Plan generation

The application should generate a structured episode plan before long-form turn generation.

The user can:

- inspect it;
- edit key fields;
- regenerate it;
- approve it;
- skip manual approval in an auto-generate workflow.

### 12.4 Budgeting

Plans should allocate approximate time/word/turn budgets per segment so the final episode does not drift arbitrarily far from target duration.

---

## 13. Conversation engine

### 13.1 Director model

Do not generate an entire long episode using one giant prompt.

Use a conversation director that advances the episode turn by turn or in small bounded groups. Conceptually:

```json
{
  "next_speaker": "priya",
  "intent": "connect the previous observation to the replication evidence",
  "evidence_ids": ["ev_17_14", "ev_22_03"],
  "target_seconds": 38,
  "handoff": "invite Daniel to challenge the causal interpretation"
}
```

The host-generation step receives the director instruction, host profile, relevant prior conversation context, and selected evidence.

### 13.2 Director responsibilities

The director should manage:

- speaker selection;
- section coverage;
- pacing;
- transitions;
- callbacks;
- evidence selection;
- balanced participation without forcing equal turns;
- avoidance of repetitive agreement;
- disagreement only when evidence or interpretation warrants it;
- conclusion/recap behavior;
- target duration.

### 13.3 Context management

Long conversations must not depend on putting the entire transcript and entire corpus into every prompt.

Maintain compact state such as:

- episode plan;
- current segment state;
- running conversation summary;
- unresolved questions;
- recent turns;
- relevant evidence;
- host interaction state.

### 13.4 Turn generation

Each generated host turn should be structured enough to retain:

- spoken text;
- evidence IDs/citations;
- intended speech characteristics if needed;
- optional interaction markers such as interruption/overlap intent;
- generation metadata.

### 13.5 Naturalness

The engine should aim for conversational delivery without deliberately inserting excessive filler or fake uncertainty. Naturalness mechanisms may include:

- short acknowledgements;
- occasional interruptions;
- callbacks;
- varied turn lengths;
- questions;
- clarification;
- concise disagreement;
- speaker-specific verbal style.

Naturalness must not undermine factual clarity or source provenance.

---

## 14. Claim verification

### 14.1 Verification stage

After dialogue generation and before final publication, the application should identify factual claims that materially depend on source evidence and evaluate their support.

### 14.2 Verification states

At minimum:

- supported;
- partially supported;
- contradicted;
- insufficient evidence;
- non-factual/opinion/transition and therefore not applicable.

### 14.3 Repair

Unsupported or contradicted material should be eligible for targeted regeneration rather than forcing a full episode regeneration.

Repairs must preserve turn/segment continuity as much as possible.

### 14.4 Claim inspector

The TUI should let the user inspect a claim, its verification state, and the supporting/contradicting source passages.

---

## 15. TTS provider system

### 15.1 Required providers

V1 must support:

- built-in KittenTTS Micro;
- OpenAI TTS;
- generic OpenAI-compatible TTS services;
- ElevenLabs.

### 15.2 KittenTTS default

KittenTTS Micro is the default built-in offline voice engine.

Requirements:

- CPU-friendly operation;
- on-demand model installation rather than bloating the base Python package;
- built-in voice discovery;
- voice preview;
- model presence/version tracking;
- a benchmark action that reports measured synthesis speed on the current machine;
- safe fallback/error reporting if the runtime or model cannot initialize.

The initial application should not require an API key or network connection after the KittenTTS model is installed and all sources are local with supplemental research disabled.

### 15.3 TTS provider contract

Conceptually:

```python
class TTSProvider(Protocol):
    async def synthesize(
        self,
        text: str,
        voice: VoiceConfig,
        options: TTSOptions,
    ) -> AudioResult: ...

    async def voices(self) -> list[VoiceInfo]: ...
    async def health(self) -> ProviderHealth: ...
```

### 15.4 Per-host provider selection

Each host may use a different TTS provider and voice within the same episode.

Changing a host's voice must not alter the host's conversational personality or epistemic role.

### 15.5 OpenAI-compatible TTS

Generic compatible services should support configurable:

- base URL;
- optional API key/headers through secure configuration;
- model;
- voice;
- response format where supported;
- timeout.

### 15.6 Voice preview

The host editor should provide a short, deterministic preview passage so users can compare voices consistently.

---

## 16. Audio pipeline

### 16.1 Canonical intermediate audio

Provider outputs should be decoded into a canonical internal PCM representation before final composition. A practical initial target is 48 kHz mono PCM for composition, with resampling from provider-native rates as needed.

### 16.2 Timeline

Represent the episode as an explicit audio timeline rather than simply concatenating compressed files.

The timeline should support:

- per-turn audio;
- pauses;
- controlled overlap/interruption;
- fades if needed;
- chapter timestamps;
- loudness normalization;
- optional intro/outro assets in a future version.

### 16.3 Exports

V1 should export at minimum:

- WAV;
- MP3;
- transcript Markdown;
- source manifest Markdown or JSON;
- machine-readable episode metadata JSON.

Opus/AAC may be added later.

### 16.4 Partial regeneration

If one turn changes, the system should regenerate that turn's TTS and recompose downstream audio without resynthesizing unaffected turns.

---

## 17. Checkpointing and resumability

### 17.1 Stage model

A generation run should have durable stages similar to:

1. validate project;
2. parse/index sources;
3. analyze corpus;
4. identify research gaps;
5. perform supplemental research;
6. build/update evidence map;
7. generate episode plan;
8. generate conversation;
9. verify/repair claims;
10. synthesize TTS;
11. compose audio;
12. export artifacts.

### 17.2 Fine-grained checkpoints

Conversation generation checkpoints at least per turn. TTS checkpoints at least per generated turn/audio artifact. Supplemental research checkpoints per research gap/query/candidate batch where practical.

### 17.3 Resume semantics

On restart, the application should explain what is complete, what is pending, and what will be recomputed.

Resume must be idempotent: already committed units should not be duplicated.

### 17.4 Cancellation and pause

Long operations should support cooperative cancellation. Pause should stop scheduling new expensive work while preserving completed state.

---

## 18. TUI information architecture

Persistent project navigation:

```text
SOURCES → RESEARCH → HOSTS → EPISODE → GENERATE → LIBRARY
```

This is not a rigid wizard. The user can revisit stages freely.

Global screens include Projects/Home, Providers, Settings, Help, and Command Palette.

### 18.1 Home / Projects

Shows projects, source counts, host counts, last episode, modification time, and any active/paused run.

Core actions:

- new project;
- open project;
- search/filter;
- rename/duplicate/delete with confirmation;
- resume an interrupted project run;
- open Providers or Settings.

### 18.2 Project overview

Shows project summary and status:

- primary source count;
- supplemental source count;
- configured hosts;
- current/draft episode;
- research policy;
- model role summary;
- obvious incomplete/setup states.

### 18.3 Sources screen

Two-pane design:

- left: primary and supplemental source list;
- right: selected-source details.

Required actions:

- add files;
- add directory;
- add URL;
- paste text;
- include/exclude;
- delete;
- inspect parsed text;
- inspect metadata/provenance;
- see parse/index state.

### 18.4 Research screen

Shows:

- research policy selector;
- research behavior toggles;
- user-entered research focus;
- corpus-analysis action;
- structured research gaps;
- per-gap Search/Ignore controls;
- bulk research action;
- research progress and candidate disposition summary.

The user must be able to see why web research is happening.

### 18.5 Hosts screen

Two-pane design:

- left: ordered host list;
- right: selected host editor.

Host editor includes:

- name;
- preset;
- role;
- trait controls;
- expertise;
- custom behavioral instructions;
- evidence priorities;
- voice provider and voice;
- preview;
- advanced relationship settings.

Actions include add, duplicate, remove, reorder, preview.

### 18.6 Episode setup screen

Includes:

- title;
- focus/instructions;
- target audience;
- technical depth;
- target duration;
- style;
- host selection;
- relevant research/citation behavior toggles;
- build plan action.

### 18.7 Episode plan screen

Displays ordered sections with duration estimates, purpose, key questions, evidence, and lead hosts.

Actions:

- edit;
- regenerate section;
- regenerate plan;
- approve and generate;
- auto-generate without approval when explicitly enabled.

### 18.8 Preflight screen

Before expensive generation, show:

- source counts;
- host count;
- expected duration;
- selected LLM role assignments;
- selected TTS providers/voices;
- provider health;
- expected dialogue size;
- cloud-cost estimate where reliable pricing information is configured/available;
- blockers/warnings.

### 18.9 Generation monitor

Shows stage checklist and live progress. During conversation generation it should display:

- section number/title;
- current turn;
- most recent host turns;
- current operation;
- progress estimate when meaningful.

Actions:

- pause;
- resume;
- cancel;
- inspect transcript;
- inspect logs/errors.

### 18.10 Episode player/review

Provides:

- playback controls where terminal capabilities permit;
- current time / total time;
- chapter navigation;
- transcript synchronized approximately to turns;
- source citations for selected/current turn;
- tabs/panes for Chapters, Transcript, Sources, Claims;
- regenerate selected section/turn;
- export.

If reliable in-terminal audio playback is not portable, the screen may launch a configured local player while retaining timeline/navigation metadata.

### 18.11 Claim inspector

Shows:

- selected statement/claim;
- verification state;
- confidence/rationale;
- supporting evidence;
- contradicting evidence;
- source origin;
- source location;
- open-source/show-passage/regenerate actions.

### 18.12 Episode library

Lists all episodes for a project including complete, draft, failed, and paused generations.

Actions:

- open/listen;
- resume;
- duplicate configuration;
- export;
- delete;
- create new episode.

### 18.13 Providers screen

Separate LLM and TTS provider lists.

Provider detail should support:

- add/edit/remove;
- endpoint/base URL;
- non-secret configuration;
- secure credential reference;
- health/test;
- discover models;
- discover voices;
- capability display.

### 18.14 Settings screen

Includes:

- data directory;
- FFmpeg location/health;
- default providers/model roles;
- default research policy;
- network/research limits;
- logging level;
- audio defaults;
- KittenTTS model management;
- cache controls.

### 18.15 Command palette and keyboard use

The application should be fully usable from the keyboard. Common actions should have discoverable shortcuts and a command palette.

Shortcuts must not be the only way to discover an action.

---

## 19. Quick workflow

After initial provider setup, the happy path should be:

```text
Create project
   ↓
Add documents
   ↓
Choose supplemental research policy
   ↓
Choose/configure 2–4 hosts
   ↓
Describe desired episode
   ↓
Review outline
   ↓
Generate
   ↓
Listen/review/export
```

Provide a **Quick Deep Dive** action using configured defaults, conceptually:

- research: Useful;
- hosts: Curious Explainer + Skeptic;
- duration: 20 minutes;
- audience: general/technically curious;
- configured default model roles;
- configured default TTS.

Quick mode must still create normal durable project/episode artifacts and remain inspectable after generation.

---

## 20. CLI

The CLI should use the same services as the TUI. Representative commands:

```bash
deeper-dive project create "My Project"
deeper-dive source add <project> paper.pdf
deeper-dive source add <project> ./papers/
deeper-dive research <project>
deeper-dive episode create <project> --title "..."
deeper-dive plan <episode>
deeper-dive generate <episode>
deeper-dive resume <episode>
deeper-dive render <episode>
deeper-dive export <episode>
deeper-dive providers test
```

A machine-readable `--json` output mode should exist for automation-oriented commands where practical.

CLI support is not a second implementation. It is another client of the application layer.

---

## 21. Provider configuration and secrets

### 21.1 Secrets

API keys must not be written into:

- project YAML/JSON;
- SQLite diagnostic tables;
- logs;
- exported manifests;
- crash reports.

Use OS keyring integration where reliable, with environment-variable references as a supported fallback. The concrete secret backend should be replaceable.

### 21.2 Config precedence

Define and document predictable precedence, for example:

1. explicit episode override;
2. project config;
3. user config;
4. environment-derived defaults.

Secrets should be referenced by logical credential IDs rather than copied into project state.

### 21.3 Local provider defaults

Expected conventional local defaults may be offered as suggestions, not assumptions:

- Ollama: localhost endpoint;
- llama-server: localhost endpoint;
- OpenAI-compatible TTS: user-defined endpoint.

Always provide a Test action.

---

## 22. KittenTTS model management

KittenTTS Micro should be downloadable on demand.

The application must track:

- expected model/runtime version;
- installed state;
- download/install errors;
- storage size where known;
- voices;
- benchmark results.

A first-run local-speech prompt may offer:

- Install KittenTTS Micro;
- Use cloud/external TTS instead;
- Configure later.

The app package itself should remain lightweight rather than embedding model weights in the Python wheel.

---

## 23. Audio benchmark

Provide a benchmark operation for local TTS.

It should:

- synthesize a deterministic representative passage;
- measure wall-clock time;
- measure output audio duration;
- report real-time factor / x-real-time speed;
- record enough runtime metadata to compare results later;
- estimate approximate TTS render time for a 20- or 30-minute episode using the measured rate.

Benchmark output is advisory, not a promise.

---

## 24. Logging, diagnostics, and observability

Logs should distinguish:

- user-facing status;
- diagnostic logs;
- provider request summaries;
- recoverable warnings;
- terminal failures.

Each generation run should have a run ID usable to correlate events.

Provider errors must retain enough sanitized detail to diagnose endpoint, model, timeout, validation, and rate-limit failures.

Offer a diagnostic export that deliberately excludes secrets and, by default, source document contents.

---

## 25. Failure handling

Expected recoverable failures include:

- malformed document;
- unsupported PDF structure;
- HTTP timeout;
- supplemental site unreachable;
- model endpoint unavailable;
- context overflow;
- invalid structured LLM response;
- rate limit;
- TTS provider failure;
- FFmpeg failure;
- disk full;
- process interruption.

A failure in one optional supplemental source should not necessarily fail the entire generation.

Retries must be bounded and classify transient vs persistent errors where practical.

The TUI must provide actionable error messages and preserve successful prior work.

---

## 26. Security and privacy

The application handles potentially private source documents. Therefore:

- do not upload source text to a cloud provider unless that stage is configured to use that provider;
- make model/provider routing inspectable before generation;
- provide a fully local path using local LLM + KittenTTS + local sources with web research disabled;
- redact secrets from logs;
- prevent automated web research from unintentionally probing private network resources;
- impose download size/time limits;
- sanitize filenames/paths used for generated artifacts;
- avoid shell interpolation when invoking FFmpeg or external players;
- document which operations send content to third parties.

A future privacy mode may enforce local-only providers at the project level; the architecture should not preclude it.

---

## 27. Testing strategy

### 27.1 Unit tests

Cover:

- domain validation;
- source deduplication;
- chunk provenance;
- research-gap state transitions;
- provider request/response normalization;
- host preset behavior data;
- director state transitions;
- checkpoint idempotency;
- audio timeline math;
- secret redaction.

### 27.2 Provider contract tests

Use mock servers/fixtures to verify OpenAI, Ollama, llama-server, OpenAI-compatible TTS, and ElevenLabs adapters without requiring real credentials in CI.

### 27.3 Integration tests

Exercise complete small pipelines using deterministic fake providers:

```text
source → parse → retrieve → plan → turns → verify → fake TTS → compose/export
```

### 27.4 TUI tests

Use Textual's testing facilities for screen navigation, widgets, keyboard actions, validation, and progress/error states.

### 27.5 Resumption tests

Inject failures between every major stage and at selected turn/TTS boundaries, reopen the project, resume, and prove that completed work is neither lost nor duplicated.

### 27.6 Real-provider smoke tests

Provide opt-in local/developer smoke tests for real providers. They must not run in normal CI without explicit credentials/runtime availability.

---

## 28. CI quality gates

The default branch should require or at least run:

- formatting/lint;
- static typing;
- unit tests;
- integration tests using fakes;
- packaging/build check;
- dependency/lock consistency check.

Tests should be deterministic and must not rely on live cloud APIs in ordinary CI.

---

## 29. Performance expectations

V1 is a local desktop/server application, not a high-throughput SaaS service. Optimize for correctness, recoverability, and user-visible progress first.

However:

- parsing/indexing should be incremental;
- unchanged sources should not be reparsed unnecessarily;
- generated turns should be cached/checkpointed;
- TTS should not regenerate unchanged turns;
- source retrieval indexes should persist;
- independent I/O-bound operations may run concurrently within provider/rate limits;
- concurrency must be bounded and configurable.

---

## 30. Versioning and reproducibility

Persist enough metadata to understand how an episode was produced:

- source hashes/snapshot;
- provider and model names;
- relevant provider configuration excluding secrets;
- host profiles;
- episode plan;
- prompt/template versions;
- application version;
- generation timestamps;
- supplemental source retrieval timestamps.

Exact deterministic reproduction is not promised for nondeterministic remote models, but configuration and provenance should be reproducible and auditable.

---

## 31. Exported source manifest

Each completed episode should be able to export a source manifest containing at least:

- all user-supplied included sources;
- all supplemental included sources;
- origin classification;
- title/author/date/URL metadata when known;
- retrieval timestamp for remote sources;
- research gap/reason for supplemental inclusion;
- whether the source materially appears in the episode;
- chapter/turn references where practical.

---

## 32. Accessibility and terminal compatibility

The TUI should:

- remain useful on common 80x24 terminals, with enhanced layouts on larger terminals;
- avoid relying on color alone for state;
- support keyboard-only operation;
- degrade gracefully when Unicode or advanced terminal capabilities are limited;
- expose textual status for progress bars and icons;
- keep core workflows usable over SSH.

---

## 33. Initial non-goals

Unless later promoted by the TODO/spec, V1 does not require:

- a web UI;
- a native desktop GUI;
- mobile apps;
- voice cloning;
- real-time live conversation with the hosts;
- multi-user collaboration;
- cloud synchronization;
- a hosted Deeper Dive backend;
- automatic publication to podcast services;
- video generation;
- exact emulation of any proprietary UI or model behavior.

The architecture should not make a future web/API frontend unnecessarily difficult, but those features must not delay the core TUI product.

---

## 34. V1 definition of done

V1 is complete when a fresh user can:

1. install Deeper Dive with documented prerequisites;
2. launch the Textual TUI;
3. create a project;
4. import multiple documents;
5. inspect parsed sources;
6. configure OpenAI, Ollama, or llama-server for LLM work;
7. optionally enable gap-driven supplemental web research;
8. review discovered supplemental sources and provenance;
9. configure at least two hosts and optionally additional hosts;
10. use preset or custom host personalities/roles;
11. preview and select KittenTTS Micro voices without a cloud TTS account;
12. optionally configure OpenAI TTS, an OpenAI-compatible TTS endpoint, or ElevenLabs;
13. create and inspect an episode plan;
14. generate a multi-host transcript using source-grounded evidence;
15. inspect citations and material claim verification;
16. synthesize and compose a complete audio episode;
17. export audio, transcript, source manifest, and metadata;
18. quit or experience a recoverable failure mid-generation and successfully resume without regenerating completed work;
19. create another episode from the same project/corpus;
20. perform the core workflow from the CLI for automation/testing purposes.

All ordinary CI quality gates must pass at the exact release head.

---

## 35. Design-change discipline

This document is the initial design authority.

During implementation, discoveries may justify changes. When a change materially alters product behavior, provider contracts, persistence, security, provenance, or the user workflow:

1. update this specification;
2. update the implementation TODO and acceptance criteria;
3. include migration/compatibility handling if persisted data is affected;
4. do not leave the code and design documents knowingly inconsistent.

The goal is not to freeze every implementation detail. The goal is to keep product intent, architecture, and implementation aligned.
