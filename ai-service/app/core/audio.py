"""Audio normalisation utilities using FFmpeg."""

import subprocess
import tempfile
from pathlib import Path


SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".webm", ".aac", ".wma"}


def normalize_audio(
    input_path: str,
    output_path: str | None = None,
    sample_rate: int = 16_000,
    max_duration_seconds: int = 45,
) -> str:
    """Convert any audio file to mono 16-bit WAV at the given sample rate.

    For files longer than *max_duration_seconds*, extract a deterministic window
    starting at 10 % of total duration (to skip intros) capped at
    *max_duration_seconds*.  This ensures repeatable embeddings for the same
    input file — a prerequisite for reliable A/B model comparisons.

    Returns the path to the normalised WAV file.
    """
    if output_path is None:
        fd, output_path = tempfile.mkstemp(suffix=".wav")
        import os
        os.close(fd)

    # Probe total duration first (fast metadata-only read)
    try:
        total = _probe_duration(input_path)
    except Exception:
        total = None  # unknown duration — just take from the start

    if total is not None and total > max_duration_seconds:
        # Deterministic: skip first 10 % of the file (avoids intros/jingles)
        start = total * 0.10
    else:
        start = 0.0

    cmd = ["ffmpeg"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += [
        "-i", str(input_path),
        "-t", str(max_duration_seconds),
        "-ac", "1",           # mono
        "-ar", str(sample_rate),
        "-sample_fmt", "s16",
        "-y",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed (exit {result.returncode}): {result.stderr.decode(errors='replace')[:500]}"
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
