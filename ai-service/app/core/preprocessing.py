"""Centralised audio preprocessing pipeline.

Every enroll / verify / search request goes through
``AudioPreprocessor.process()`` which enforces a deterministic sequence:

  1. FFmpeg normalise (mono 16 kHz s16 WAV)
  2. Vocal / music separation  (Demucs)
  3. Noise reduction            (noisereduce spectral gating)
  4. VAD speech extraction
  5. Length normalisation        (repeat-pad short / segment long)

The output is a :class:`PreprocessResult` containing one or more fixed-length
waveform segments ready for the embedder, plus metadata about what happened.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from app.config import Settings
from app.core.audio import normalize_audio, repeat_pad, segment_waveform
from app.core.denoise import Denoiser
from app.core.separator import VocalSeparator
from app.core.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16_000


class PreprocessError(Exception):
    """Raised when audio cannot be preprocessed into usable speech."""


@dataclass
class PreprocessResult:
    """Output of the preprocessing pipeline."""

    segments: list[np.ndarray]          # one or more fixed-length waveforms
    analysis_waveform: np.ndarray       # speech waveform after VAD, before pad/segment
    total_speech_seconds: float         # total seconds of speech detected by VAD
    timings: dict[str, float] = field(default_factory=dict)
    options: dict[str, bool] = field(default_factory=dict)
    num_segments: int = field(init=False)

    def __post_init__(self):
        self.num_segments = len(self.segments)


class AudioPreprocessor:
    """Orchestrate the mandatory preprocessing pipeline."""

    def __init__(
        self,
        vad: VoiceActivityDetector,
        separator: VocalSeparator,
        denoiser: Denoiser,
        cfg: Settings,
    ):
        self.vad = vad
        self.separator = separator
        self.denoiser = denoiser
        self.cfg = cfg

    def process(
        self,
        raw_wav_path: str,
        *,
        separate_vocals: bool | None = None,
        denoise: bool | None = None,
        collect_timings: bool = False,
    ) -> tuple[PreprocessResult, list[str]]:
        """Run the full pipeline on *raw_wav_path*.

        Returns ``(result, cleanup_dirs)`` where *cleanup_dirs* is a list of
        temp directories the caller must ``shutil.rmtree`` after use.

        Raises :class:`PreprocessError` when no usable speech is found.
        """
        cleanup_dirs: list[str] = []
        timings: dict[str, float] = {}
        total_started = time.perf_counter()
        use_separation = self.cfg.preprocess_separate_vocals if separate_vocals is None else separate_vocals
        use_denoise = self.cfg.preprocess_denoise if denoise is None else denoise

        # 1. Normalise → mono 16 kHz WAV
        step_started = time.perf_counter()
        wav_path = normalize_audio(
            raw_wav_path,
            max_duration_seconds=self.cfg.preprocess_normalize_max_seconds,
        )
        if collect_timings:
            timings["normalize"] = round(time.perf_counter() - step_started, 4)

        # 2. Vocal separation (strip background music)
        if use_separation:
            step_started = time.perf_counter()
            vocals_path, sep_dir = self.separator.separate(wav_path)
            cleanup_dirs.append(sep_dir)
            if collect_timings:
                timings["separate"] = round(time.perf_counter() - step_started, 4)
            if vocals_path != wav_path:
                # Demucs (htdemucs) outputs at 44100 Hz regardless of input
                # sample rate.  Re-normalise back to 16 kHz so that the Silero
                # VAD model (which only accepts 16 kHz) sees the correct audio.
                step_started = time.perf_counter()
                wav_path = normalize_audio(
                    vocals_path,
                    max_duration_seconds=self.cfg.preprocess_normalize_max_seconds,
                )
                if collect_timings:
                    timings["renormalize_after_separation"] = round(time.perf_counter() - step_started, 4)

        # 3. Noise reduction
        if use_denoise:
            step_started = time.perf_counter()
            wav_path = self._denoise_file(wav_path)
            if collect_timings:
                timings["denoise"] = round(time.perf_counter() - step_started, 4)

        # 4. VAD — extract speech
        step_started = time.perf_counter()
        speech = self.vad.extract_speech(
            wav_path,
            min_speech_seconds=self.cfg.preprocess_min_speech_seconds,
            max_speech_seconds=self.cfg.preprocess_max_speech_seconds,
            fallback_to_raw=not use_separation,
        )
        if collect_timings:
            timings["vad"] = round(time.perf_counter() - step_started, 4)

        if speech is None:
            if self.cfg.preprocess_reject_no_speech:
                raise PreprocessError(
                    "No usable speech detected in the audio. "
                    "The file may be pure music, silence, or too noisy."
                )
            # Fallback: read the normalised wav directly (backward compat path)
            import scipy.io.wavfile as _wavfile
            _, raw_data = _wavfile.read(wav_path)
            if raw_data.ndim > 1:
                raw_data = raw_data[:, 0]
            speech = raw_data.astype(np.float32) / 32768.0
            limit = int(self.cfg.preprocess_max_speech_seconds * SAMPLE_RATE)
            speech = speech[:limit]

        analysis_waveform = speech.copy()
        total_speech_seconds = len(speech) / SAMPLE_RATE

        # 5. Length normalisation
        min_samples = int(self.cfg.preprocess_min_speech_seconds * SAMPLE_RATE)
        seg_samples = int(self.cfg.preprocess_segment_length_seconds * SAMPLE_RATE)
        step_samples = int(self.cfg.preprocess_segment_step_seconds * SAMPLE_RATE)

        step_started = time.perf_counter()
        if len(speech) < min_samples and self.cfg.preprocess_short_repeat:
            speech = repeat_pad(speech, min_samples)

        if len(speech) <= seg_samples:
            segments = [speech]
        else:
            segments = segment_waveform(speech, seg_samples, step_samples)

        if collect_timings:
            timings["segment"] = round(time.perf_counter() - step_started, 4)
            timings["total"] = round(time.perf_counter() - total_started, 4)

        return PreprocessResult(
            segments=segments,
            analysis_waveform=analysis_waveform,
            total_speech_seconds=total_speech_seconds,
            timings=timings,
            options={
                "separate_vocals": use_separation,
                "denoise": use_denoise,
            },
        ), cleanup_dirs

    # ------------------------------------------------------------------
    def _denoise_file(self, wav_path: str) -> str:
        """Read wav, denoise in-memory, write back to the same path."""
        import scipy.io.wavfile as _wavfile

        rate, data = _wavfile.read(wav_path)
        if data.ndim > 1:
            data = data[:, 0]
        float_data = data.astype(np.float32) / 32768.0

        clean = self.denoiser.reduce(float_data, sample_rate=rate)

        # Write back as 16-bit WAV (same format FFmpeg produced)
        int16 = (np.clip(clean, -1.0, 1.0) * 32767).astype(np.int16)
        _wavfile.write(wav_path, rate, int16)
        return wav_path
