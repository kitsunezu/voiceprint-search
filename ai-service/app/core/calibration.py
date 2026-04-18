"""Score calibration — convert cosine similarity to probability."""

from __future__ import annotations

import numpy as np
from scipy.special import expit  # sigmoid

from app.config import ModelConfig


class ScoreCalibrator:
    """Logistic calibration: P(same_speaker) = sigmoid(weight * score + bias).

    Default parameters are a reasonable starting point for ECAPA-TDNN on
    VoxCeleb-style data.  Re-fit on your own validation pairs for best results.
    """

    def __init__(self, weight: float = 10.0, bias: float = -3.5):
        self.weight = weight
        self.bias = bias

    def calibrate(self, score: float) -> float:
        """Map a cosine similarity in [-1, 1] to a probability in [0, 1]."""
        logit = self.weight * score + self.bias
        return float(expit(logit))

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> None:
        """Re-fit calibration from labelled (score, same_speaker?) pairs.

        Requires scikit-learn (not a hard runtime dep).
        """
        from sklearn.linear_model import LogisticRegression

        lr = LogisticRegression(solver="lbfgs")
        lr.fit(scores.reshape(-1, 1), labels.astype(int))
        self.weight = float(lr.coef_[0][0])
        self.bias = float(lr.intercept_[0])


class CalibratorRegistry:
    """Per-model calibrator lookup."""

    def __init__(self):
        self._calibrators: dict[str, ScoreCalibrator] = {}

    def register(self, cfg: ModelConfig) -> None:
        self._calibrators[cfg.id] = ScoreCalibrator(
            weight=cfg.calibration_weight,
            bias=cfg.calibration_bias,
        )

    def get(self, model_id: str) -> ScoreCalibrator:
        cal = self._calibrators.get(model_id)
        if cal is None:
            return ScoreCalibrator()  # fallback to default
        return cal
