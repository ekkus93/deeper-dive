from __future__ import annotations

from deeper_dive.research_policy import (
    ResearchControls,
    ResearchMode,
    ResearchPolicy,
    ResearchPolicyStore,
)
from deeper_dive.storage.database import Database


def test_modes_controls_overrides_and_restart(tmp_path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    store = ResearchPolicyStore(database)

    default = store.project("p1")
    assert default.mode is ResearchMode.USEFUL
    assert default.automated_search_allowed

    controls = ResearchControls(
        find_newer_research=False,
        contradictory_evidence=True,
        missing_citations=False,
        prefer_primary_sources=True,
        replication_review_evidence=False,
        background_context=True,
        permit_general_interest=True,
    )
    conservative = ResearchPolicy(ResearchMode.CONSERVATIVE, controls)
    store.set_project("p1", conservative)
    assert store.episode("p1", "e1") == conservative

    off = ResearchPolicy(ResearchMode.OFF, controls)
    store.set_episode("e1", off)
    assert store.episode("p1", "e1") == off
    assert not store.episode("p1", "e1").automated_search_allowed

    reopened = ResearchPolicyStore(Database(tmp_path / "project.db"))
    assert reopened.project("p1") == conservative
    assert reopened.episode("p1", "e1") == off

    reopened.set_episode("e1", None)
    assert reopened.episode("p1", "e1") == conservative


def test_all_research_modes_are_supported() -> None:
    assert {mode.value for mode in ResearchMode} == {
        "off",
        "conservative",
        "useful",
        "aggressive",
    }
