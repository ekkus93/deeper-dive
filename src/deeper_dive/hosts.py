"""Editable host profiles and data-driven preset factories."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from deeper_dive.storage.episode_repositories import HostProfileRecord


@dataclass(slots=True)
class HostProfile:
    """Normal editable host representation produced by presets and custom creation."""

    id: str
    project_id: str
    display_name: str
    preset_origin: str | None = None
    role: str = ""
    expertise: str = ""
    instructions: str = ""
    behavior: dict[str, float | str | bool] = field(default_factory=dict)
    evidence_priorities: list[str] = field(default_factory=list)
    tts_provider: str | None = None
    tts_voice: str | None = None

    def to_record(self) -> HostProfileRecord:
        return HostProfileRecord(
            id=self.id,
            project_id=self.project_id,
            display_name=self.display_name,
            preset_origin=self.preset_origin,
            role=self.role,
            expertise=self.expertise,
            instructions=self.instructions,
            behavior_json=json.dumps(self.behavior, sort_keys=True),
            evidence_priorities_json=json.dumps(self.evidence_priorities),
            tts_provider=self.tts_provider,
            tts_voice=self.tts_voice,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


PRESET_DEFINITIONS: dict[str, dict[str, Any]] = {
    "curious_explainer": {
        "display_name": "Curious Explainer",
        "role": "Explainer",
        "instructions": "Ask clarifying questions and make difficult ideas understandable.",
        "behavior": {"curiosity": 0.9, "technicality": 0.55, "question_frequency": 0.8},
        "evidence_priorities": ["clarity", "primary corpus"],
    },
    "skeptic": {
        "display_name": "Skeptic",
        "role": "Skeptic",
        "instructions": "Probe caveats, counterevidence, contradictions, and methodological limits.",
        "behavior": {"skepticism": 0.95, "assertiveness": 0.65, "question_frequency": 0.75},
        "evidence_priorities": ["counterevidence", "methodology", "contradictions"],
    },
    "synthesizer": {
        "display_name": "Synthesizer",
        "role": "Synthesizer",
        "instructions": "Connect evidence across sources and reconcile compatible perspectives.",
        "behavior": {"curiosity": 0.7, "technicality": 0.6, "analogy_use": 0.55},
        "evidence_priorities": ["cross-source connections", "consensus and disagreement"],
    },
    "domain_expert": {
        "display_name": "Domain Expert",
        "role": "Domain Expert",
        "instructions": "Emphasize mechanisms, terminology, technical precision, and evidentiary limits.",
        "behavior": {"technicality": 0.95, "verbosity": 0.65, "assertiveness": 0.6},
        "evidence_priorities": ["primary sources", "mechanisms", "technical precision"],
    },
    "practitioner": {
        "display_name": "Practitioner",
        "role": "Practitioner",
        "instructions": "Translate evidence into practical implications, constraints, and tradeoffs.",
        "behavior": {"technicality": 0.6, "analogy_use": 0.45, "verbosity": 0.5},
        "evidence_priorities": ["practical implications", "real-world constraints"],
    },
    "historian": {
        "display_name": "Historian",
        "role": "Historian",
        "instructions": "Establish chronology and documented intellectual or institutional context.",
        "behavior": {"verbosity": 0.65, "technicality": 0.55, "curiosity": 0.65},
        "evidence_priorities": ["chronology", "primary historical evidence", "context"],
    },
    "moderator": {
        "display_name": "Moderator",
        "role": "Moderator",
        "instructions": "Manage turn-taking, transitions, unresolved questions, and balanced participation.",
        "behavior": {"assertiveness": 0.55, "question_frequency": 0.65, "verbosity": 0.35},
        "evidence_priorities": ["unresolved questions", "conversation coverage"],
    },
    "custom": {
        "display_name": "Custom",
        "role": "Custom",
        "instructions": "",
        "behavior": {},
        "evidence_priorities": [],
    },
}


def preset_names() -> tuple[str, ...]:
    return tuple(PRESET_DEFINITIONS)


def create_host_from_preset(
    preset: str, project_id: str, *, host_id: str | None = None
) -> HostProfile:
    """Return a fresh normal HostProfile; preset definitions are never returned by reference."""

    if preset not in PRESET_DEFINITIONS:
        raise KeyError(preset)
    data = deepcopy(PRESET_DEFINITIONS[preset])
    return HostProfile(
        id=host_id or str(uuid4()),
        project_id=project_id,
        preset_origin=preset,
        **data,
    )
