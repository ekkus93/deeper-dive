"""Minimal partial TTS invalidation and timeline regeneration."""

from __future__ import annotations

from dataclasses import dataclass

from deeper_dive.audio_timeline import AudioTimeline, TimelineItem
from deeper_dive.tts_generation import TTSArtifact, TTSGenerationStage, TTSTurn


@dataclass(frozen=True, slots=True)
class RegeneratedAudio:
    artifacts: tuple[TTSArtifact, ...]
    timeline: AudioTimeline


class PartialAudioRegenerator:
    """Regenerate only turns whose TTS identity changed and rebuild timing metadata."""

    def __init__(self, stage: TTSGenerationStage) -> None:
        self.stage = stage

    def regenerate(
        self,
        *,
        run_id: str,
        episode_id: str,
        turns: tuple[TTSTurn, ...],
        pauses_after: dict[str, float] | None = None,
        overlaps: dict[str, float] | None = None,
    ) -> RegeneratedAudio:
        artifacts = self.stage.generate(run_id, turns)
        by_turn = {artifact.turn_id: artifact for artifact in artifacts}
        pauses_after = pauses_after or {}
        overlaps = overlaps or {}
        items: list[TimelineItem] = []
        for turn in turns:
            artifact = by_turn[turn.turn_id]
            duration = self._duration_for(artifact, turn)
            items.append(
                TimelineItem.clip(
                    turn_id=turn.turn_id,
                    host_id=turn.host_id,
                    artifact_id=artifact.artifact_id,
                    duration_seconds=duration,
                    overlap_previous_seconds=overlaps.get(turn.turn_id, 0.0),
                )
            )
            pause = pauses_after.get(turn.turn_id, 0.0)
            if pause:
                items.append(TimelineItem.pause(pause))
        return RegeneratedAudio(artifacts, AudioTimeline.build(episode_id, tuple(items)))

    @staticmethod
    def _duration_for(artifact: TTSArtifact, turn: TTSTurn) -> float:
        # Duration is intentionally derived from the current artifact bytes where possible later;
        # this conservative text estimate keeps timeline rebuild deterministic for opaque formats.
        words = max(1, len(turn.text.split()))
        return words / 150 * 60
