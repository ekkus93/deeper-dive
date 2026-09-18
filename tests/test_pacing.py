from __future__ import annotations

from deeper_dive.pacing import DurationPacingController, PacingPolicy, PacingState


def _words(count: int) -> str:
    return " ".join(f"w{i}" for i in range(count))


def test_estimates_spoken_duration_from_default_and_voice_baselines() -> None:
    controller = DurationPacingController(PacingPolicy(words_per_minute=120))
    assert controller.estimate_spoken_seconds(_words(120)) == 60
    assert controller.estimate_spoken_seconds(_words(180), words_per_minute=180) == 60


def test_tracks_actual_words_and_adapts_remaining_budget() -> None:
    controller = DurationPacingController(PacingPolicy(words_per_minute=120))
    state = controller.record_turn(PacingState(target_seconds=120), _words(60))
    decision = controller.decide(state, desired_turn_seconds=45)
    assert state.generated_words == 60
    assert state.turn_count == 1
    assert decision.estimated_spoken_seconds == 30
    assert decision.remaining_seconds == 90
    assert decision.remaining_words == 180
    assert decision.next_turn_words == 90


def test_too_verbose_model_is_bounded_by_word_budget() -> None:
    controller = DurationPacingController(PacingPolicy(words_per_minute=120))
    state = controller.record_turn(PacingState(target_seconds=60), _words(200))
    decision = controller.decide(state)
    assert decision.hard_stop
    assert decision.should_complete
    assert decision.remaining_words == 0
    assert decision.next_turn_words == 0


def test_too_terse_model_is_bounded_by_hard_turn_limit() -> None:
    controller = DurationPacingController(
        PacingPolicy(words_per_minute=120, max_turns_per_segment=3)
    )
    state = PacingState(target_seconds=300)
    for _ in range(3):
        state = controller.record_turn(state, "brief")
    decision = controller.decide(state)
    assert decision.hard_stop
    assert decision.should_complete
    assert state.turn_count == 3


def test_content_exhaustion_permits_concise_early_completion() -> None:
    controller = DurationPacingController(PacingPolicy(words_per_minute=120))
    state = controller.record_turn(PacingState(target_seconds=300), _words(30))
    decision = controller.decide(state, content_exhausted=True)
    assert decision.should_complete
    assert not decision.hard_stop
    assert decision.next_turn_words == 0
