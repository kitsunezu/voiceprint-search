"""Speaker-verification decision policy.

Cosine similarity is a model score, not a probability.  A conservative
three-way policy avoids turning every borderline score into a biometric
accept/reject claim.
"""

from __future__ import annotations

from typing import Literal


VerificationDecision = Literal["same", "different", "inconclusive"]


def classify_similarity(
    score: float,
    *,
    different_threshold: float,
    same_threshold: float,
) -> VerificationDecision:
    """Classify *score* using separate reject and accept thresholds."""
    if different_threshold >= same_threshold:
        raise ValueError("different_threshold must be lower than same_threshold")
    if score >= same_threshold:
        return "same"
    if score < different_threshold:
        return "different"
    return "inconclusive"


def should_fast_return(
    score: float,
    *,
    different_threshold: float,
    margin: float,
    separation_requested: bool,
) -> bool:
    """Return early only for a clearly negative cheap-path result.

    A high cheap-path score must never be accepted without the requested vocal
    separation.  This is important for singing voices, where accompaniment and
    similar vocal style can create spuriously high cosine scores.
    """
    if not separation_requested:
        return True
    safe_margin = max(0.0, float(margin))
    return score < (different_threshold - safe_margin)
