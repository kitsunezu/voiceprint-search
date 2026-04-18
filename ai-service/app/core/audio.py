"""Audio normalisation utilities using FFmpeg."""

import os
import subprocess
import tempfile
from pathlib import Path


SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".webm", ".aac", ".wma"}


def resolve_trim_window(
    total_duration_seconds: float | None,
    max_duration_seconds: int | float | None,
) -> tuple[float, float | None]:
    """Return a deterministic trim window for long audio inputs."""
    if max_duration_seconds is None:
        return 0.0, None

    limit = float(max_duration_seconds)
    if limit <= 0:
        return 0.0, None

    if total_duration_seconds is None:
        return 0.0, limit

    if total_duration_seconds <= limit:
        return 0.0, None

    # Skip the earliest intro/jingle portion, but never run past the file end.
    start = min(total_duration_seconds * 0.10, total_duration_seconds - limit)
    return start, limit


def normalize_audio(
    input_path: str,
    output_path: str | None = None,
    sample_rate: int = 16_000,
    max_duration_seconds: int | float | None = 240,
) -> str:
    """Convert any audio file to mono 16-bit WAV at the given sample rate.

    When *max_duration_seconds* is set, long files are reduced to a
    deterministic window that starts at 10 % of the total duration to skip
    common intros. Passing ``None`` or ``<= 0`` keeps the full input.

    Returns the path to the normalised WAV file.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(
            suffix=".wav",
            dir=os.path.dirname(os.path.abspath(input_path)) or None,
        )
        os.close(fd)

    # Probe total duration first (fast metadata-only read)
    try:
        total = _probe_duration(input_path)
    except Exception:
        total = None  # unknown duration — just take from the start

    start, limit = resolve_trim_window(total, max_duration_seconds)

    cmd = ["ffmpeg"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += [
        "-i", str(input_path),
        "-ac", "1",           # mono
        "-ar", str(sample_rate),
        "-sample_fmt", "s16",
        "-y",
        output_path,
    ]
    if limit is not None:
        cmd[cmd.index("-ac"):cmd.index("-ac")] = ["-t", f"{limit:.3f}"]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed (exit {result.returncode}): {result.stderr.decode(errors='replace')[:500]}"
        )
    return output_path


def render_playback_audio(
    input_path: str,
    output_path: str,
    sample_rate: int = 44_100,
    max_duration_seconds: int | float | None = 240,
) -> str:
    """Render a user-facing WAV while preserving channel layout.

    This is intentionally separate from ``normalize_audio``: playback audio
    should remain higher fidelity than the mono 16 kHz analysis pipeline used
    for VAD and embeddings.
    """
    try:
        total = _probe_duration(input_path)
    except Exception:
        total = None

    start, limit = resolve_trim_window(total, max_duration_seconds)

    cmd = ["ffmpeg"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += [
        "-i", str(input_path),
    ]
    if limit is not None:
        cmd += ["-t", f"{limit:.3f}"]
    cmd += [
        "-vn",
        "-ar", str(sample_rate),
        "-c:a", "pcm_s16le",
        "-y",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg playback render failed (exit {result.returncode}): {result.stderr.decode(errors='replace')[:500]}"
        )
    return output_path


def _probe_duration(file_path: str) -> float:
    """Return total duration in seconds via FFprobe (fast metadata read)."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"FFprobe failed: {result.stderr[:300]}")
    return float(result.stdout.strip())


def get_audio_duration(file_path: str) -> float:
    """Return the duration of an audio file in seconds via FFprobe."""
    return _probe_duration(file_path)


def validate_extension(filename: str) -> bool:
    """Check if the file extension is in the supported set."""
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


# ── Length normalisation helpers ──────────────────────────────────────────


def repeat_pad(waveform: "np.ndarray", min_samples: int) -> "np.ndarray":
    """Repeat-pad *waveform* until it reaches at least *min_samples* length."""
    import numpy as np

    if len(waveform) >= min_samples:
        return waveform
    reps = (min_samples // len(waveform)) + 1
    return np.tile(waveform, reps)[:min_samples]


def segment_waveform(
    waveform: "np.ndarray",
    segment_samples: int,
    step_samples: int,
) -> "list[np.ndarray]":
    """Split *waveform* into overlapping fixed-length segments.

    The last segment is zero-padded if shorter than *segment_samples*.
    Returns at least one segment.
    """
    import numpy as np

    segments: list[np.ndarray] = []
    start = 0
    while start < len(waveform):
        end = start + segment_samples
        seg = waveform[start:end]
        if len(seg) < segment_samples:
            seg = np.pad(seg, (0, segment_samples - len(seg)))
        segments.append(seg)
        start += step_samples
    return segments
