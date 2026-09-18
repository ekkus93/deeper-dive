from __future__ import annotations

import pytest

from deeper_dive.hosts import HostProfile, HostRelationship
from deeper_dive.storage.database import Database
from deeper_dive.storage.episode_repositories import HostEpisodeRepository


def test_host_behavior_validates_traits_preferences_and_profile_fields() -> None:
    host = HostProfile(
        "h1",
        "p1",
        "Expert",
        role="critic",
        expertise="biology",
        instructions="Prefer mechanistic explanations.",
        behavior={
            "curiosity": 0.7,
            "turn_length": 0.4,
            "question_frequency": 0.6,
            "analogy_use": 0.3,
            "interruption": 0.1,
        },
        evidence_priorities=["primary studies", "methods"],
    )
    record = host.to_record()
    restored = HostProfile.from_record(record)
    assert restored.role == "critic"
    assert restored.expertise == "biology"
    assert restored.behavior["turn_length"] == 0.4
    assert restored.evidence_priorities == ["primary studies", "methods"]

    with pytest.raises(ValueError, match="between 0 and 1"):
        HostProfile("bad", "p1", "Bad", behavior={"skepticism": 1.1})
    with pytest.raises(ValueError, match="must be numeric"):
        HostProfile("bad", "p1", "Bad", behavior={"question_frequency": "often"})


def test_three_host_relationship_graph_persists_and_produces_prompt_context(tmp_path) -> None:
    repository = HostEpisodeRepository(Database(tmp_path / "project.db"))
    hosts = [HostProfile(f"h{i}", "p1", f"Host {i}") for i in range(1, 4)]
    for host in hosts:
        repository.create_host(host.to_record())

    relationships = [
        HostRelationship("p1", "h1", "h2", "challenge", "Probe assumptions.", 0.4),
        HostRelationship("p1", "h2", "h3", "mentor", "Explain technical gaps.", 0.8),
        HostRelationship("p1", "h3", "h1", "synthesize", "Connect historical context.", 0.7),
    ]
    for relationship in relationships:
        repository.upsert_relationship(relationship.to_record())

    restored = [HostRelationship.from_record(row) for row in repository.list_relationships("p1")]
    assert {(item.from_host_id, item.to_host_id) for item in restored} == {
        ("h1", "h2"),
        ("h2", "h3"),
        ("h3", "h1"),
    }
    assert "Probe assumptions." in restored[0].prompt_context()
    assert "affinity=" in restored[0].prompt_context()


def test_relationship_rejects_self_edges_and_invalid_affinity() -> None:
    with pytest.raises(ValueError, match="distinct hosts"):
        HostRelationship("p1", "h1", "h1")
    with pytest.raises(ValueError, match="between 0 and 1"):
        HostRelationship("p1", "h1", "h2", affinity=-0.1)
