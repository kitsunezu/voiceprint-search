"""CPU-first noise reduction using spectral gating (noisereduce).

This module wraps the ``noisereduce`` library which is a lightweight,
CPU-friendly denoiser based on spectral gating — suitable for removing
background hiss, hum, and recording-device artefacts.

Usage::

    denoiser = Denoiser()
    clean = denoiser.reduce(waveform, sample_rate=16_000)
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class Denoiser:
    """Spectral-gating noise reduction (CPU-only, no model download)."""

    def reduce(
        self,
        waveform: np.ndarray,
        sample_rate: int = 16_000,
    ) -> np.ndarray:
        """Return a denoised copy of *waveform* (1-D float32/float64).

        On any failure the original waveform is returned unchanged so the
        pipeline degrades gracefully.
        """
        try:
            import noisereduce as nr

            reduced = nr.reduce_noise(
                y=waveform,
                sr=sample_rate,
                stationary=False,   # non-stationary handles music bleed better
                prop_decrease=0.75,
            )
            return np.asarray(reduced, dtype=waveform.dtype)
        except Exception:
            logger.exception("Noise reduction failed — falling back to original audio.")
            return waveform
