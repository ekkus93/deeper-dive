from pathlib import Path

from deeper_dive.audio_regeneration import PartialAudioRegenerator
from deeper_dive.tts import FakeTTSProvider, TTSProviderRegistry
from deeper_dive.tts_generation import TTSArtifact, TTSGenerationStage, TTSTurn


class MemoryArtifacts:
    def __init__(self) -> None:
        self.by_key: dict[str, TTSArtifact] = {}

    def get_by_cache_key(self, key: str) -> TTSArtifact | None:
        return self.by_key.get(key)

    def save(self, artifact: TTSArtifact) -> None:
        self.by_key[artifact.cache_key] = artifact

    def mark_checkpoint(self, run_id: str, turn_id: str) -> None:
        pass


def test_changing_one_turn_reuses_unrelated_tts_and_rebuilds_timestamps(tmp_path: Path) -> None:
    provider = FakeTTSProvider()
    registry = TTSProviderRegistry()
    registry.register(provider)
    repository = MemoryArtifacts()
    stage = TTSGenerationStage(registry, repository, tmp_path, max_workers=1)  # type: ignore[arg-type]
    regenerator = PartialAudioRegenerator(stage)
    original = (
        TTSTurn("t1", "h1", "one two", "fake-tts", "voice-a"),
        TTSTurn("t2", "h2", "three four", "fake-tts", "voice-a"),
    )
    first = regenerator.regenerate(run_id="r", episode_id="e", turns=original)
    assert len(provider.requests) == 2
    changed = (
        original[0],
        TTSTurn("t2", "h2", "three four five six seven", "fake-tts", "voice-a"),
    )
    second = regenerator.regenerate(run_id="r", episode_id="e", turns=changed)
    assert len(provider.requests) == 3
    assert second.artifacts[0].artifact_id == first.artifacts[0].artifact_id
    assert second.artifacts[1].artifact_id != first.artifacts[1].artifact_id
    assert second.timeline.duration_seconds > first.timeline.duration_seconds


def test_voice_or_settings_change_invalidates_only_affected_turn(tmp_path: Path) -> None:
    provider = FakeTTSProvider()
    registry = TTSProviderRegistry()
    registry.register(provider)
    repository = MemoryArtifacts()
    stage = TTSGenerationStage(registry, repository, tmp_path, max_workers=1)  # type: ignore[arg-type]
    regenerator = PartialAudioRegenerator(stage)
    base = (TTSTurn("t1", "h", "hello world", "fake-tts", "voice-a"),)
    regenerator.regenerate(run_id="r", episode_id="e", turns=base)
    changed = (TTSTurn("t1", "h", "hello world", "fake-tts", "voice-a", settings={"sample_rate_hz": 16000}),)
    regenerator.regenerate(run_id="r", episode_id="e", turns=changed)
    assert len(provider.requests) == 2
