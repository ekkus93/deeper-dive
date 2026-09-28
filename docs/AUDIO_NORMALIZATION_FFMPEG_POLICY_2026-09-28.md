# Audio Normalization FFmpeg Policy

Deeper Dive normalizes provider TTS audio to a single canonical composition contract before timeline and episode-audio assembly:

- format: signed 16-bit little-endian PCM (`pcm_s16le`);
- sample rate: 24 kHz;
- channels: mono;
- accepted production composition artifact format: WAV.

Production normalization uses FFmpeg/libswresample through `FFmpegAudioNormalizer`; nearest-neighbor resampling is not used for WAV or raw PCM provider output. MP3 output remains rejected by preflight under the WAV-only composition policy, so unsupported formats fail before expensive TTS synthesis whenever provider configuration is known.

Mandatory CI covers the FFmpeg-backed normalization path in `tests/test_audio_normalization.py`, including 12 kHz stereo WAV conversion and a second nontrivial 44.1 kHz conversion without exact PCM assertions. The fresh-machine workflow installs `ffmpeg` before exercising installed-wheel CLI/TUI and generation/export paths, so the dependency is explicitly present for clean-environment qualification.
