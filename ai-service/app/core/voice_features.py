"""Lightweight voice-characteristic extraction for frontend visualisation."""

from __future__ import annotations

import math

import numpy as np

EPS = 1e-8
FRAME_LENGTH = 640
HOP_LENGTH = 320


def _clip01(value: float) -> float:
    return float(max(0.0, min(1.0, value)))


def _normalize(value: float, minimum: float, maximum: float) -> float:
    if maximum <= minimum:
        return 0.0
    return _clip01((value - minimum) / (maximum - minimum))


def _frame_signal(
    waveform: np.ndarray,
    frame_length: int = FRAME_LENGTH,
    hop_length: int = HOP_LENGTH,
) -> np.ndarray:
    wave = np.asarray(waveform, dtype=np.float32).flatten()
    if wave.size == 0:
        return np.zeros((0, frame_length), dtype=np.float32)

    if wave.size < frame_length:
        wave = np.pad(wave, (0, frame_length - wave.size))

    starts = list(range(0, max(wave.size - frame_length, 0) + 1, hop_length))
    if not starts:
        starts = [0]
    last_start = wave.size - frame_length
    if starts[-1] != last_start:
        starts.append(last_start)

    return np.stack([wave[start:start + frame_length] for start in starts]).astype(np.float32)


def _pitch_stats(frames: np.ndarray, sample_rate: int) -> tuple[float, float, float]:
    min_lag = max(1, int(sample_rate / 350.0))
    max_lag = max(min_lag + 1, int(sample_rate / 80.0))

    pitches: list[float] = []
    confidences: list[float] = []

    for frame in frames:
        centered = frame - float(np.mean(frame))
        energy = float(np.sqrt(np.mean(centered ** 2) + EPS))
        if energy < 0.01:
            continue

        corr = np.correlate(centered, centered, mode="full")[centered.size - 1:]
        zero_lag = float(corr[0]) + EPS
        window = corr[min_lag:max_lag + 1]
        if window.size == 0:
            continue

        peak_index = int(np.argmax(window))
        peak = float(window[peak_index])
        confidence = peak / zero_lag
        if confidence < 0.15:
            continue

        lag = peak_index + min_lag
        pitches.append(float(sample_rate / lag))
        confidences.append(_clip01((confidence - 0.15) / 0.45))

    if not pitches:
        return 0.0, 0.0, 0.0

    return (
        float(np.median(pitches)),
        float(np.std(pitches)),
        float(np.median(confidences)),
    )


def extract_voice_characteristics(
    waveform: np.ndarray,
    sample_rate: int = 16_000,
) -> dict[str, float]:
    frames = _frame_signal(waveform)
    if frames.size == 0:
        return {
            "pitch_hz": 0.0,
            "brightness_hz": 0.0,
            "warmth_ratio": 0.0,
            "clarity_score": 0.0,
            "stability_score": 0.0,
        }

    window = np.hanning(frames.shape[1]).astype(np.float32)
    windowed = frames * window
    spectrum = np.abs(np.fft.rfft(windowed, axis=1)) ** 2
    freqs = np.fft.rfftfreq(frames.shape[1], d=1.0 / sample_rate)
    energy = spectrum.sum(axis=1) + EPS

    centroid = np.sum(spectrum * freqs, axis=1) / energy
    flatness = np.exp(np.mean(np.log(spectrum + EPS), axis=1)) / (np.mean(spectrum + EPS, axis=1))
    low_band_ratio = np.sum(spectrum[:, freqs <= 1_000.0], axis=1) / energy

    rms = np.sqrt(np.mean(frames ** 2, axis=1) + EPS)
    rms_mean = float(np.mean(rms))
    rms_cv = float(np.std(rms) / (rms_mean + EPS))

    pitch_mean, pitch_std, harmonic_strength = _pitch_stats(frames, sample_rate)
    pitch_cv = pitch_std / pitch_mean if pitch_mean > 0 else 1.0

    flatness_score = 1.0 - _normalize(float(np.mean(flatness)), 0.12, 0.55)
    clarity_score = _clip01((0.65 * harmonic_strength) + (0.35 * flatness_score))
    stability_score = 1.0 - _clip01((0.6 * _normalize(pitch_cv, 0.05, 0.45)) + (0.4 * _normalize(rms_cv, 0.08, 0.55)))

    return {
        "pitch_hz": round(pitch_mean, 1),
        "brightness_hz": round(float(np.mean(centroid)), 1),
        "warmth_ratio": round(float(np.mean(low_band_ratio)), 4),
        "clarity_score": round(clarity_score, 4),
        "stability_score": round(stability_score, 4),
    }


def compare_voice_characteristics(
    waveform_a: np.ndarray,
    waveform_b: np.ndarray,
    sample_rate: int = 16_000,
) -> dict[str, object]:
    metrics_a = extract_voice_characteristics(waveform_a, sample_rate=sample_rate)
    metrics_b = extract_voice_characteristics(waveform_b, sample_rate=sample_rate)

    dimensions = [
        {
            "key": "pitch",
            "audio_a": _normalize(metrics_a["pitch_hz"], 85.0, 300.0),
            "audio_b": _normalize(metrics_b["pitch_hz"], 85.0, 300.0),
            "audio_a_value": metrics_a["pitch_hz"],
            "audio_b_value": metrics_b["pitch_hz"],
            "unit": "Hz",
        },
        {
            "key": "brightness",
            "audio_a": _normalize(metrics_a["brightness_hz"], 700.0, 2_800.0),
            "audio_b": _normalize(metrics_b["brightness_hz"], 700.0, 2_800.0),
            "audio_a_value": metrics_a["brightness_hz"],
            "audio_b_value": metrics_b["brightness_hz"],
            "unit": "Hz",
        },
        {
            "key": "warmth",
            "audio_a": _normalize(metrics_a["warmth_ratio"], 0.25, 0.85),
            "audio_b": _normalize(metrics_b["warmth_ratio"], 0.25, 0.85),
            "audio_a_value": metrics_a["warmth_ratio"],
            "audio_b_value": metrics_b["warmth_ratio"],
            "unit": "ratio",
        },
        {
            "key": "clarity",
            "audio_a": metrics_a["clarity_score"],
            "audio_b": metrics_b["clarity_score"],
            "audio_a_value": metrics_a["clarity_score"],
            "audio_b_value": metrics_b["clarity_score"],
            "unit": "ratio",
        },
        {
            "key": "stability",
            "audio_a": metrics_a["stability_score"],
            "audio_b": metrics_b["stability_score"],
            "audio_a_value": metrics_a["stability_score"],
            "audio_b_value": metrics_b["stability_score"],
            "unit": "ratio",
        },
    ]

    diffs = [abs(float(item["audio_a"]) - float(item["audio_b"])) for item in dimensions]
    profile_similarity = round(max(0.0, 1.0 - float(np.mean(diffs))), 4)
    if profile_similarity >= 0.85:
        summary = "high"
    elif profile_similarity >= 0.68:
        summary = "medium"
    else:
        summary = "low"

    for item in dimensions:
        item["difference"] = round(abs(float(item["audio_a"]) - float(item["audio_b"])), 4)

    return {
        "profile_similarity": profile_similarity,
        "summary": summary,
        "dimensions": dimensions,
    }