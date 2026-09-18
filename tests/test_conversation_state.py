from pathlib import Path

from deeper_dive.conversation_state import ConversationState, ConversationStateRepository
from deeper_dive.storage.database import Database, LATEST_SCHEMA_VERSION


def test_conversation_state_round_trips_and_resumes_after_reopen(tmp_path: Path) -> None:
    path = tmp_path / "project.db"
    database = Database(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES ('p','P','t','t')"
        )
        connection.execute(
            """INSERT INTO episodes(
                id,project_id,title,created_at,modified_at
            ) VALUES ('e','p','Episode','t','t')"""
        )

    repository = ConversationStateRepository(database)
    repository.save(
        ConversationState(
            episode_id="e",
            segment_ordinal=2,
            segment_turn=7,
            running_summary="We established the baseline and found one unresolved conflict.",
            unresolved_topics=("conflicting study", "follow-up question"),
            recent_context_refs=("turn-19", "chunk-42"),
            participation={"host-a": 5, "host-b": 4},
        )
    )

    reopened = ConversationStateRepository(Database(path)).get("e")
    assert reopened is not None
    assert reopened.segment_ordinal == 2
    assert reopened.segment_turn == 7
    assert "baseline" in reopened.running_summary
    assert reopened.unresolved_topics == ("conflicting study", "follow-up question")
    assert reopened.recent_context_refs == ("turn-19", "chunk-42")
    assert reopened.participation == {"host-a": 5, "host-b": 4}


def test_conversation_state_partial_update_preserves_other_advisory_state(tmp_path: Path) -> None:
    database = Database(tmp_path / "project.db")
    database.initialize()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO projects(id,name,created_at,modified_at) VALUES ('p','P','t','t')"
        )
        connection.execute(
            "INSERT INTO episodes(id,project_id,title,created_at,modified_at) VALUES ('e','p','E','t','t')"
        )
    repository = ConversationStateRepository(database)
    repository.save(
        ConversationState("e", running_summary="summary", participation={"host-a": 2})
    )
    updated = repository.update("e", segment_ordinal=1, segment_turn=3)
    assert updated.running_summary == "summary"
    assert updated.participation == {"host-a": 2}
    assert updated.segment_ordinal == 1
    assert updated.segment_turn == 3
