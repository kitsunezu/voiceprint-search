"""Voice Activity Detection using Silero VAD."""

import torch
import numpy as np
import scipy.io.wavfile as _wavfile


class VoiceActivityDetector:
    """Detect speech segments in a 16 kHz mono WAV."""

    def __init__(self):
        self.model, self._utils = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            trust_repo=True,
        )
        (
            self.get_speech_timestamps,
            _,
            _read_audio_unused,
            _,
            _,
        ) = self._utils

    def _read_wav(self, wav_path: str) -> torch.Tensor:
        """Read a 16-bit mono WAV produced by FFmpeg and return a float32 tensor.

        Bypasses torchaudio (which broke in v2.9+) by using scipy.io.wavfile.
        """
        _rate, data = _wavfile.read(wav_path)
        if data.ndim > 1:
            data = data[:, 0]  # take first channel if somehow stereo
        data = data.astype(np.float32) / 32768.0
        return torch.from_numpy(data)

    def detect_speech(
        self,
        wav_path: str,
        threshold: float = 0.5,
        sampling_rate: int = 16_000,
    ) -> tuple[list[dict], torch.Tensor]:
        """Return (timestamps, waveform_tensor) for the given WAV file."""
        wav = self._read_wav(wav_path)
        timestamps = self.get_speech_timestamps(
            wav, self.model, threshold=threshold, sampling_rate=sampling_rate,
        )
        return timestamps, wav

    def extract_speech(
        self,
        wav_path: str,
        min_speech_seconds: float = 0.5,
        max_speech_seconds: float = 30.0,
        fallback_to_raw: bool = False,
    ) -> np.ndarray | None:
        """Extract and concatenate speech segments up to *max_speech_seconds*.

        Stops collecting segments early once enough speech has been gathered —
        this avoids processing entire long recordings (e.g. 2-hour videos) when
        30 s of speech is already sufficient for a reliable speaker embedding.

        Returns ``None`` when no usable speech is found and *fallback_to_raw*
        is ``False`` (the default).  When *fallback_to_raw* is ``True`` the
        first *max_speech_seconds* of the full waveform are returned instead —
        this preserves backward-compatible behaviour for callers that opt in.
        """
        timestamps, wav = self.detect_speech(wav_path)

        if timestamps:
            segments: list[torch.Tensor] = []
            total_samples = 0
            limit_samples = int(max_speech_seconds * 16_000)
            for ts in timestamps:
                seg = wav[ts["start"]:ts["end"]]
                segments.append(seg)
                total_samples += len(seg)
                if total_samples >= limit_samples:
                    break  # enough speech collected — early exit

            speech = torch.cat(segments)
            if speech.shape[0] / 16_000 >= min_speech_seconds:
                return speech.numpy()

        if fallback_to_raw:
            limit_samples = int(max_speech_seconds * 16_000)
            return wav[:limit_samples].numpy()

        # No usable speech detected
        return None
