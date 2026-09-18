"""Editable host profiles, validated behavior, relationships, and preset factories."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4

from deeper_dive.storage.episode_repositories import HostProfileRecord, HostRelationshipRecord

TRAIT_KEYS = frozenset({"curiosity", "skepticism", "technicality", "assertiveness", "verbosity"})
PREFERENCE_KEYS = frozenset({"turn_length", "question_frequency", "analogy_use", "interruption"})
BOUNDED_BEHAVIOR_KEYS = TRAIT_KEYS | PREFERENCE_KEYS


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

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Reject malformed behavior before it can enter persistence or prompt assembly."""
        if not self.display_name.strip():
            raise ValueError("host display_name must not be empty")
        for key, value in self.behavior.items():
            if key in BOUNDED_BEHAVIOR_KEYS:
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"host behavior {key!r} must be numeric")
                if not 0.0 <= float(value) <= 1.0:
                    raise ValueError(f"host behavior {key!r} must be between 0 and 1")
        if any(not priority.strip() for priority in self.evidence_priorities):
            raise ValueError("evidence priorities must not contain empty values")

    def to_record(self) -> HostProfileRecord:
        self.validate()
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

    @classmethod
    def from_record(cls, record: HostProfileRecord) -> HostProfile:
        return cls(
            id=record.id,
            project_id=record.project_id,
            display_name=record.display_name,
            preset_origin=record.preset_origin,
            role=record.role,
            expertise=record.expertise,
            instructions=record.instructions,
            behavior=json.loads(record.behavior_json),
            evidence_priorities=json.loads(record.evidence_priorities_json),
            tts_provider=record.tts_provider,
            tts_voice=record.tts_voice,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class HostRelationship:
    """Directed relationship guidance from one participating host to another."""

    project_id: str
    from_host_id: str
    to_host_id: str
    stance: str = "peer"
    instructions: str = ""
    affinity: float = 0.5

    def __post_init__(self) -> None:
        if self.from_host_id == self.to_host_id:
            raise ValueError("host relationship must connect distinct hosts")
        if not 0.0 <= self.affinity <= 1.0:
            raise ValueError("host relationship affinity must be between 0 and 1")
        if not self.stance.strip():
            raise ValueError("host relationship stance must not be empty")

    def to_record(self) -> HostRelationshipRecord:
        payload = {
            "affinity": self.affinity,
            "instructions": self.instructions,
            "stance": self.stance,
        }
        return HostRelationshipRecord(
            project_id=self.project_id,
            from_host_id=self.from_host_id,
            to_host_id=self.to_host_id,
            relationship_json=json.dumps(payload, sort_keys=True),
        )

    @classmethod
    def from_record(cls, record: HostRelationshipRecord) -> HostRelationship:
        payload = json.loads(record.relationship_json)
        return cls(
            project_id=record.project_id,
            from_host_id=record.from_host_id,
            to_host_id=record.to_host_id,
            stance=str(payload.get("stance", "peer")),
            instructions=str(payload.get("instructions", "")),
            affinity=float(payload.get("affinity", 0.5)),
        )

    def prompt_context(self) -> str:
        """Stable compact representation suitable for later host prompt assembly."""
        context = f"Relationship to {self.to_host_id}: {self.stance}; affinity={self.affinity:.2f}"
        return f"{context}; {self.instructions}" if self.instructions else context


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
        "instructions": (
            "Probe caveats, counterevidence, contradictions, and methodological limits."
        ),
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
        "instructions": (
            "Emphasize mechanisms, terminology, technical precision, and evidentiary limits."
        ),
        "behavior": {"technicality": 0.95, "verbosity": 0.65, "assertiveness": 0.6},
        "evidence_priorities": ["primary sources", "mechanisms", "technical precision"],
    },
    "practitioner": {
        "display_name": "Practitioner",
        "role": "Practitioner",
        "instructions": (
            "Translate evidence into practical implications, constraints, and tradeoffs."
        ),
        "behavior": {"technicality": 0.6, "analogy_use": 0.45, "verbosity": 0.5},
        "evidence_priorities": ["practical implications", "real-world constraints"],
    },
    "historian": {
        "display_name": "Historian",
        "role": "Historian",
        "instructions": (
            "Establish chronology and documented intellectual or institutional context."
        ),
        "behavior": {"verbosity": 0.65, "technicality": 0.55, "curiosity": 0.65},
        "evidence_priorities": ["chronology", "primary historical evidence", "context"],
    },
    "moderator": {
        "display_name": "Moderator",
        "role": "Moderator",
        "instructions": (
            "Manage turn-taking, transitions, unresolved questions, and balanced participation."
        ),
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
