"""Duration estimation and adaptive bounded pacing for generated conversation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PacingPolicy:
    words_per_minute: float = 144.0
    max_turns_per_segment: int = 12
    min_turns_before_early_completion: int = 1
    minimum_turn_words: int = 20

    def __post_init__(self) -> None:
        if self.words_per_minute <= 0:
            raise ValueError("words_per_minute must be positive")
        if self.max_turns_per_segment < 1:
            raise ValueError("max_turns_per_segment must be positive")
        if self.min_turns_before_early_completion < 0:
            raise ValueError("min_turns_before_early_completion cannot be negative")
        if self.minimum_turn_words < 1:
            raise ValueError("minimum_turn_words must be positive")


@dataclass(frozen=True, slots=True)
class PacingState:
    target_seconds: int
    generated_words: int = 0
    turn_count: int = 0

    def __post_init__(self) -> None:
        if self.target_seconds <= 0:
            raise ValueError("target_seconds must be positive")
        if self.generated_words < 0 or self.turn_count < 0:
            raise ValueError("pacing counters cannot be negative")


@dataclass(frozen=True, slots=True)
class PacingDecision:
    estimated_spoken_seconds: float
    remaining_seconds: float
    remaining_words: int
    next_turn_words: int
    should_complete: bool
    hard_stop: bool


class DurationPacingController:
    """Track generated words and adapt the remaining segment budget."""

    def __init__(self, policy: PacingPolicy | None = None) -> None:
        self.policy = policy or PacingPolicy()

    def estimate_spoken_seconds(self, text: str, *, words_per_minute: float | None = None) -> float:
        rate = self.policy.words_per_minute if words_per_minute is None else words_per_minute
        if rate <= 0:
            raise ValueError("voice words_per_minute must be positive")
        return len(text.split()) * 60.0 / rate

    def record_turn(self, state: PacingState, text: str) -> PacingState:
        return PacingState(
            target_seconds=state.target_seconds,
            generated_words=state.generated_words + len(text.split()),
            turn_count=state.turn_count + 1,
        )

    def decide(
        self,
        state: PacingState,
        *,
        content_exhausted: bool = False,
        desired_turn_seconds: int = 45,
    ) -> PacingDecision:
        if desired_turn_seconds <= 0:
            raise ValueError("desired_turn_seconds must be positive")
        estimated = state.generated_words * 60.0 / self.policy.words_per_minute
        remaining_seconds = max(0.0, state.target_seconds - estimated)
        target_words = round(state.target_seconds * self.policy.words_per_minute / 60.0)
        remaining_words = max(0, target_words - state.generated_words)
        hard_stop = state.turn_count >= self.policy.max_turns_per_segment or remaining_words == 0
        early = (
            content_exhausted
            and state.turn_count >= self.policy.min_turns_before_early_completion
        )
        should_complete = hard_stop or early
        nominal_words = round(desired_turn_seconds * self.policy.words_per_minute / 60.0)
        next_turn_words = 0 if should_complete else min(remaining_words, max(self.policy.minimum_turn_words, nominal_words))
        return PacingDecision(
            estimated_spoken_seconds=estimated,
            remaining_seconds=remaining_seconds,
            remaining_words=remaining_words,
            next_turn_words=next_turn_words,
            should_complete=should_complete,
            hard_stop=hard_stop,
        )
