from pathlib import Path
from unittest.mock import patch

import pytest

from deeper_dive.audio_timeline import AudioTimeline, TimelineItem
from deeper_dive.ffmpeg import FFmpegComposer, FFmpegConfig, FFmpegError


def test_compose_uses_argv_without_shell_interpolation(tmp_path: Path) -> None:
    dangerous = tmp_path / "clip; echo pwned $(touch nope).wav"
    dangerous.write_bytes(b"audio")
    output = tmp_path / "output file.wav"
    timeline = AudioTimeline.build(
        "episode",
        (TimelineItem.clip(turn_id="t", host_id="h", artifact_id="a", duration_seconds=1.0),),
    )
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        FFmpegComposer(FFmpegConfig(Path("/usr/bin/ffmpeg"))).compose(
            timeline, {"a": dangerous}, output
        )
    args = run.call_args.args[0]
    assert str(dangerous) in args
    assert str(output) in args
    assert run.call_args.kwargs["shell"] is False


def test_compose_applies_timeline_delay_and_loudness(tmp_path: Path) -> None:
    first = tmp_path / "one.wav"
    second = tmp_path / "two.wav"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    timeline = AudioTimeline.build(
        "e",
        (
            TimelineItem.clip(turn_id="t1", host_id="h", artifact_id="a", duration_seconds=1),
            TimelineItem.pause(0.5),
            TimelineItem.clip(turn_id="t2", host_id="h", artifact_id="b", duration_seconds=1),
        ),
    )
    with patch("subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stderr = ""
        FFmpegComposer(FFmpegConfig(Path("ffmpeg"))).compose(
            timeline, {"a": first, "b": second}, tmp_path / "out.wav"
        )
    filter_graph = run.call_args.args[0][run.call_args.args[0].index("-filter_complex") + 1]
    assert "adelay=1500:all=1" in filter_graph
    assert "loudnorm=I=-16.0:TP=-1.5" in filter_graph


def test_failure_sanitizes_stderr() -> None:
    with patch("subprocess.run") as run:
        run.return_value.returncode = 1
        run.return_value.stderr = "token=secret-value decoder exploded"
        with pytest.raises(FFmpegError, match=r"token=\[redacted\].*decoder exploded"):
            FFmpegComposer._run(["ffmpeg", "input"])
