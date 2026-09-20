# Research and provenance

Deeper Dive separates user-supplied evidence from supplemental research so that generated episodes remain inspectable. This guide explains how primary sources, supplemental sources, research gaps, citations, and claim verification should be interpreted.

## Primary vs supplemental sources

Primary sources are the documents, pasted text, directories, or explicit URLs that the user adds to a project. They are the authoritative starting corpus for an episode. Their origin is recorded as user-supplied material, and generated plans, turns, claims, citations, and exports should preserve enough metadata to identify which project source and passage supported a statement.

Supplemental sources are discovered or accepted through the research workflow. They are never meant to silently become primary material. A supplemental source should retain the research gap or question that motivated it, the candidate outcome that accepted or rejected it, and enough provenance to explain why it was included. The user should be able to distinguish “this was in my corpus” from “the application found this while investigating a gap.”

Explicit user URL imports are treated as user-supplied sources because the user chose the URL directly. Automated supplemental research is separate and must use the research-safe fetch boundary rather than the explicit URL import path.

## Research modes

Research is optional and policy-driven. A project can be used without supplemental web research; in that mode, the episode should be grounded in the existing project corpus and should surface limitations when the corpus is insufficient.

When research is enabled, the controller first analyzes the current corpus for explicit gaps. Examples include missing background context, outdated material, absent corroboration, missing cited works, contradictory sources, or audience-specific explanation needs. The research stage should then work from those gaps instead of issuing arbitrary searches.

Common policies are:

- **None/local-only**: do not perform supplemental web research; rely on current project sources and local artifacts.
- **Useful**: identify material gaps and research selected gaps when doing so materially improves the episode.
- **Explicit/selected**: let the user inspect gaps and choose which ones to research.

The implementation may expose these policies through the TUI, CLI, or episode configuration, but the provenance principle is the same: supplemental research must remain attributable to a concrete gap.

## Research-gap workflow

The normal gap workflow is:

1. Analyze the included primary corpus for missing or weak evidence.
2. Persist research gaps with status and rationale.
3. Let the user list, ignore, or research gaps.
4. Fetch bounded candidate documents through the research-safe network boundary.
5. Record candidate outcomes, including accepted/rejected status and rationale.
6. Import accepted supplemental material with its origin and motivating gap.
7. Make accepted supplemental evidence available to planning, generation, citation, and claim inspection while preserving origin.

The CLI supports this automation path with `research analyze`, `research gaps`, `research run`, `research ignore`, and `research outcomes`. The TUI should present the same lifecycle in a more inspectable form.

Ignored gaps are a user decision, not proof that the underlying issue is resolved. If the source corpus changes, the application may need to re-run gap analysis and invalidate stale gap decisions where appropriate.

## Source-quality limitations

Source inclusion is not a guarantee of truth. A source can be outdated, incomplete, low-quality, contradictory, duplicated, or irrelevant to the episode focus. Supplemental research can reduce some uncertainty, but it can also introduce new uncertainty if the candidate source is weak.

Generated content should avoid presenting evidence as stronger than the underlying sources justify. A skeptic or reviewer host can probe weak support, but host personality should not override source quality. When sources disagree, the conversation should surface the disagreement instead of flattening it into a single unsupported conclusion.

Automated research also has network limits. The research-safe fetch boundary rejects unsafe schemes and non-public network targets and enforces redirect, timeout, content-type, and size limits. These controls reduce risk, but they do not guarantee that every useful source is discoverable or that every fetched source is reliable.

## Citations and evidence mapping

Citations should point back to source chunks or passages rather than only to a source title. A useful citation answers:

- which source was used;
- whether it was primary or supplemental;
- where in that source the evidence appeared;
- which generated turn or claim depends on it.

A generated turn may cite multiple evidence chunks, and a source chunk may support multiple turns or claims. Exported transcripts and review screens should preserve those many-to-many links where available.

Missing citations should be treated as a review signal. They do not automatically prove that text is wrong, but they do mean the user cannot inspect the support chain without additional review or regeneration.

## Claim verification limits

Claim verification is a quality-control pass over generated statements. It can identify claims, attach supporting or contradicting evidence, and classify verification state. It is not an oracle and cannot prove global truth.

Important limits:

- It only checks against available project and supplemental evidence.
- It can miss implicit claims or split/merge claims imperfectly.
- It can mark a claim unsupported because evidence is absent, not because the claim is false.
- It can surface contradictions without resolving which source is better.
- It should not hide detailed diagnostics or provenance from the user.

A supported claim is best understood as “supported by the available evidence links,” not as an unconditional guarantee. An unsupported or contradicted claim should be reviewed, edited, regenerated, or removed before relying on the episode output.

## Practical review checklist

Before treating an episode as ready to export or share, review:

- whether the episode relies mainly on the intended primary sources;
- which supplemental sources were added and why;
- whether research gaps remain ignored or unresolved;
- whether important generated turns have citations;
- whether material claims are supported or contradicted;
- whether source limitations and disagreements are represented fairly.

This review is intentionally part of the product workflow. Deeper Dive is designed to make provenance visible, not to remove human judgment from source-grounded synthesis.
