"""Deterministic episode export artifacts with provenance and secret-safe metadata."""

from __future__ import annotations

import json
import re
import wave
from dataclasses import asdict, dataclass
from pathlib import Path

from deeper_dive.audio_normalization import CanonicalAudio
from deeper_dive.ffmpeg import FFmpegComposer

# fmt: off


@dataclass(frozen=True, slots=True)
class TranscriptClaim:
    claim_id: str
    text: str
    state: str = "unverified"
    rationale: str = ""
    supporting_ids: tuple[str, ...] = ()
    contradicting_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TranscriptSourcePassage:
    chunk_id: str
    source_title: str
    origin: str
    location: str | None = None
    text: str = ""
    relation: str = "cited"


@dataclass(frozen=True, slots=True)
class TranscriptTurn:
    host: str
    text: str
    turn_id: str = ""
    speaker_id: str = ""
    segment_ordinal: int = 0
    turn_ordinal: int = 0
    evidence_ids: tuple[str, ...] = ()
    claims: tuple[TranscriptClaim, ...] = ()
    source_passages: tuple[TranscriptSourcePassage, ...] = ()


@dataclass(frozen=True, slots=True)
class ManifestSource:
    title: str
    origin: str
    locator: str | None = None


class EpisodeExporter:
    """Write the complete portable artifact set for one episode."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def reserve_stem(self, title: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "episode"
        candidate = self.output_dir / slug
        suffix = 2
        while any(candidate.with_suffix(ext).exists() for ext in (".wav", ".mp3", ".md", ".json")):
            candidate = self.output_dir / f"{slug}-{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def write_wav(path: Path, audio: CanonicalAudio) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as output:
            output.setnchannels(audio.channels)
            output.setsampwidth(audio.sample_width_bytes)
            output.setframerate(audio.sample_rate_hz)
            output.writeframes(audio.pcm)
        return path

    @staticmethod
    def write_mp3(wav_path: Path, mp3_path: Path, composer: FFmpegComposer) -> Path:
        composer._run([str(composer.config.executable), "-y", "-i", str(wav_path), str(mp3_path)])
        return mp3_path

    @classmethod
    def write_transcript(cls, path: Path, title: str, turns: tuple[TranscriptTurn, ...]) -> Path:
        body = [f"# {title}", ""]
        for turn in turns:
            body.extend(cls._turn_markdown(turn))
        path.write_text("\n".join(body), encoding="utf-8")
        return path

    @staticmethod
    def write_manifest(path: Path, sources: tuple[ManifestSource, ...]) -> Path:
        payload = {"sources": [asdict(source) for source in sources]}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    @staticmethod
    def write_metadata(path: Path, metadata: dict[str, object]) -> Path:
        forbidden = {"api_key", "apikey", "token", "authorization", "password", "secret"}

        def clean(value: object) -> object:
            if isinstance(value, dict):
                return {
                    str(key): clean(item)
                    for key, item in value.items()
                    if str(key).lower().replace("-", "_") not in forbidden
                }
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value

        path.write_text(json.dumps(clean(metadata), indent=2, sort_keys=True), encoding="utf-8")
        return path

    @staticmethod
    def transcript_provenance(turns: tuple[TranscriptTurn, ...]) -> dict[str, object]:
        return {
            "turns": [
                {
                    "turn_id": turn.turn_id,
                    "chapter": turn.segment_ordinal + 1,
                    "segment_ordinal": turn.segment_ordinal,
                    "turn_ordinal": turn.turn_ordinal,
                    "host": turn.host,
                    "speaker_id": turn.speaker_id,
                    "citations": list(turn.evidence_ids),
                    "claims": [asdict(claim) for claim in turn.claims],
                    "source_passages": [asdict(passage) for passage in turn.source_passages],
                }
                for turn in turns
            ]
        }

    @staticmethod
    def _turn_markdown(turn: TranscriptTurn) -> list[str]:
        heading = f"## {turn.host}"
        if turn.turn_id:
            heading = (
                f"## Chapter {turn.segment_ordinal + 1} / "
                f"Turn {turn.turn_ordinal + 1}: {turn.host}"
            )
        lines = [heading, ""]
        if turn.turn_id:
            lines.extend(
                (
                    f"Turn ID: {turn.turn_id}",
                    f"Speaker ID: {turn.speaker_id}",
                    "Citations: " + (", ".join(turn.evidence_ids) if turn.evidence_ids else "none"),
                    "",
                )
            )
        lines.extend((turn.text, ""))
        if turn.claims:
            lines.extend(("### Claims", ""))
            for claim in turn.claims:
                evidence = tuple(dict.fromkeys((*claim.supporting_ids, *claim.contradicting_ids)))
                lines.extend(
                    (
                        f"- [{claim.state}] {claim.text}",
                        f"  - Claim ID: {claim.claim_id}",
                        f"  - Evidence: {', '.join(evidence) if evidence else 'none'}",
                    )
                )
                if claim.rationale:
                    lines.append(f"  - Rationale: {claim.rationale}")
            lines.append("")
        if turn.source_passages:
            lines.extend(("### Source passages", ""))
            for passage in turn.source_passages:
                location = passage.location or "location unavailable"
                lines.extend(
                    (
                        f"- [{passage.chunk_id}] {passage.relation} | {passage.origin} | "
                        f"{passage.source_title} | {location}",
                        f"  {passage.text}",
                    )
                )
            lines.append("")
        return lines

# fmt: on
