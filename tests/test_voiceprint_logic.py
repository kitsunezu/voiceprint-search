from __future__ import annotations

import sys
import asyncio
import unittest
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "ai-service"))

from app.config import Settings
from app.core.audio import select_evenly_spaced_segments
from app.core.decision import classify_similarity, should_fast_return
from app.core.preprocessing import PreprocessResult
from app.core.reference_profiles import build_reference_profile, compare_reference_profiles
from app.core.verify_service import run_verify_pipeline


@dataclass
class FakeEmbedding:
    id: int
    audio_asset_id: int
    vector: list[float]
    weight: float = 1.0


class FakeSeparator:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def separate(self, path: str, *, max_duration_seconds=...) -> tuple[str, str]:
        self.calls.append((path, max_duration_seconds))
        return f"{path}.vocals.wav", f"{path}.separator"


class FakePreprocessor:
    def __init__(self) -> None:
        self.separator = FakeSeparator()
        self.calls: list[tuple[str, bool | None]] = []

    def process(
        self,
        path: str,
        *,
        separate_vocals: bool | None = None,
        **_options,
    ):
        self.calls.append((path, separate_vocals))
        result = PreprocessResult(
            segments=[np.ones(16_000, dtype=np.float32)],
            analysis_waveform=np.ones(16_000, dtype=np.float32),
            playback_source_path=path,
            total_speech_seconds=1.0,
        )
        return result, []


class FakeEmbedder:
    model_id = "fake"
    embedding_dim = 2

    def __init__(self, score: float) -> None:
        self.score = score

    def embed(self, waveform: np.ndarray, sample_rate: int = 16_000) -> np.ndarray:
        return np.array([1.0, 0.0], dtype=np.float32)

    def similarity(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        return self.score


class FakeCalibrator:
    is_fitted = False

    def calibrate(self, score: float) -> float:
        return 0.5


class DecisionPolicyTests(unittest.TestCase):
    def test_three_way_decision_boundaries(self) -> None:
        thresholds = {"different_threshold": 0.35, "same_threshold": 0.90}
        self.assertEqual(classify_similarity(0.20, **thresholds), "different")
        self.assertEqual(classify_similarity(0.35, **thresholds), "inconclusive")
        self.assertEqual(classify_similarity(0.70, **thresholds), "inconclusive")
        self.assertEqual(classify_similarity(0.90, **thresholds), "same")

    def test_fast_return_never_accepts_high_score_when_separation_requested(self) -> None:
        self.assertTrue(
            should_fast_return(
                0.20,
                different_threshold=0.35,
                margin=0.0,
                separation_requested=True,
            )
        )
        self.assertFalse(
            should_fast_return(
                0.95,
                different_threshold=0.35,
                margin=0.0,
                separation_requested=True,
            )
        )

    def test_fast_path_only_returns_early_for_clear_negative(self) -> None:
        async def run(score: float):
            preprocessor = FakePreprocessor()
            with patch(
                "app.core.verify_service.compare_voice_characteristics",
                return_value=None,
            ):
                response = await run_verify_pipeline(
                    path_a="a.wav",
                    path_b="b.wav",
                    speaker_id=None,
                    model_id="fake",
                    threshold=0.90,
                    different_threshold=0.35,
                    separate_vocals=True,
                    denoise=True,
                    include_timings=False,
                    enable_fast_return=True,
                    fast_return_margin=0.0,
                    embedder=FakeEmbedder(score),
                    calibrator=FakeCalibrator(),
                    preprocessor=preprocessor,
                )
            return response, preprocessor

        negative, negative_preprocessor = asyncio.run(run(0.20))
        inconclusive, inconclusive_preprocessor = asyncio.run(run(0.70))
        high, high_preprocessor = asyncio.run(run(0.95))

        self.assertEqual(negative["strategy"], "fast-return")
        self.assertEqual(negative["decision"], "different")
        self.assertFalse(negative["is_same_speaker"])
        self.assertEqual(len(negative_preprocessor.calls), 2)
        self.assertEqual(inconclusive["strategy"], "full")
        self.assertEqual(inconclusive["decision"], "inconclusive")
        self.assertIsNone(inconclusive["is_same_speaker"])
        self.assertEqual(len(inconclusive_preprocessor.calls), 4)
        self.assertEqual(high["strategy"], "full")
        self.assertEqual(high["decision"], "same")
        self.assertTrue(high["is_same_speaker"])
        self.assertEqual(len(high_preprocessor.calls), 4)


class SegmentBudgetTests(unittest.TestCase):
    def test_even_sampling_preserves_clip_coverage(self) -> None:
        segments = [np.array([index]) for index in range(60)]
        selected = select_evenly_spaced_segments(segments, 12)
        values = [int(segment[0]) for segment in selected]
        self.assertEqual(len(values), 12)
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 59)
        self.assertEqual(values, sorted(set(values)))


class ReferenceProfileTests(unittest.TestCase):
    def test_profile_score_uses_equal_weight_asset_prototypes(self) -> None:
        profile_a = [
            FakeEmbedding(1, 10, [1.0, 0.0]),
            FakeEmbedding(2, 10, [1.0, 0.0]),
            FakeEmbedding(3, 11, [0.0, 1.0]),
        ]
        profile_b = [
            FakeEmbedding(4, 20, [1.0, 0.0]),
            FakeEmbedding(5, 21, [0.0, 1.0]),
        ]

        comparison = compare_reference_profiles(profile_a, profile_b)
        legacy_a = np.average(
            np.stack([np.array(row.vector) for row in profile_a]),
            axis=0,
            weights=[row.weight for row in profile_a],
        )
        legacy_b = np.average(
            np.stack([np.array(row.vector) for row in profile_b]),
            axis=0,
            weights=[row.weight for row in profile_b],
        )
        legacy_score = float(
            np.dot(legacy_a, legacy_b)
            / (np.linalg.norm(legacy_a) * np.linalg.norm(legacy_b))
        )
        self.assertAlmostEqual(comparison.score, 1.0, places=6)
        self.assertAlmostEqual(comparison.centroid_score, 1.0, places=6)
        self.assertGreater(comparison.score, legacy_score + 0.05)
        self.assertEqual(comparison.asset_count_a, 2)
        self.assertEqual(comparison.asset_count_b, 2)

    def test_long_enrollment_separates_each_short_representative_window(self) -> None:
        preprocessor = FakePreprocessor()
        cfg = Settings(
            preprocess_separate_vocals=True,
            profile_window_seconds=30,
            profile_max_windows=4,
        )

        with (
            patch("app.core.reference_profiles.get_audio_duration", return_value=180.0),
            patch(
                "app.core.reference_profiles.extract_audio_window",
                side_effect=lambda path, *, start_seconds, duration_seconds: (
                    f"{path}.{start_seconds:.0f}-{duration_seconds:.0f}.wav"
                ),
            ),
        ):
            windows, _, duration = build_reference_profile(
                "long.webm",
                preprocessor=preprocessor,
                cfg=cfg,
            )

        self.assertEqual(duration, 180.0)
        self.assertEqual(len(windows), 4)
        self.assertEqual(preprocessor.separator.calls, [])
        self.assertTrue(all(separate is True for _, separate in preprocessor.calls))


if __name__ == "__main__":
    unittest.main()
