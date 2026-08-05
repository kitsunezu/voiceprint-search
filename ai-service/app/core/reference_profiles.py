"""Reference-profile helpers for long-form enrollment assets."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import os

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.audio import extract_audio_window, get_audio_duration, plan_profile_windows
from app.core.embedder import EmbedderRegistry, embed_segments, weighted_average_embeddings
from app.core.preprocessing import AudioPreprocessor, PreprocessError
from app.db import repository as repo
from app.db.models import Embedding


@dataclass
class ReferenceProfileWindow:
    index: int
    start_seconds: float
    duration_seconds: float
    speech_seconds: float
    weight: float
    segments: list[np.ndarray]


@dataclass(frozen=True)
class ReferenceProfileComparison:
    """Robust comparison of two multi-asset reference profiles."""

    score: float
    coverage_score: float
    centroid_score: float
    asset_count_a: int
    asset_count_b: int


def compute_profile_weight(speech_seconds: float, *, power: float) -> float:
    exponent = max(float(power), 0.0)
    usable_seconds = max(float(speech_seconds), 0.1)
    if exponent == 0.0:
        return 1.0
    return usable_seconds ** exponent


def build_reference_profile(
    raw_audio_path: str,
    *,
    preprocessor: AudioPreprocessor,
    cfg: Settings = settings,
) -> tuple[list[ReferenceProfileWindow], list[str], float | None]:
    """Build one or more weighted profile windows from a raw audio asset."""
    shared_source_path = raw_audio_path
    shared_cleanup_dirs: list[str] = []

    try:
        total_duration = get_audio_duration(raw_audio_path)
    except Exception:
        total_duration = None

    # Only separate the whole source when it fits in one profile window.  Long
    # assets are sampled first and each short representative window is then
    # separated.  This keeps long and short enrollments in the same data domain
    # without running Demucs across an entire multi-hour stream.
    should_use_shared_separation = cfg.preprocess_separate_vocals and (
        total_duration is None or total_duration <= float(cfg.profile_window_seconds)
    )

    if should_use_shared_separation:
        shared_source_path, sep_dir = preprocessor.separator.separate(raw_audio_path, max_duration_seconds=None)
        shared_cleanup_dirs.append(sep_dir)
    planned = plan_profile_windows(
        total_duration,
        window_seconds=cfg.profile_window_seconds,
        max_windows=cfg.profile_max_windows,
        skip_intro_ratio=cfg.profile_skip_intro_ratio,
    )

    profile_windows: list[ReferenceProfileWindow] = []
    cleanup_dirs: list[str] = list(shared_cleanup_dirs)

    for window in planned:
        use_shared_source = (
            window.index == 0
            and abs(window.start_seconds) < 0.001
            and (total_duration is None or total_duration <= window.duration_seconds + 0.001)
        )
        window_path = shared_source_path
        if not use_shared_source:
            window_path = extract_audio_window(
                shared_source_path,
                start_seconds=window.start_seconds,
                duration_seconds=window.duration_seconds,
            )

        try:
            result, pp_dirs = preprocessor.process(
                window_path,
                separate_vocals=cfg.preprocess_separate_vocals and not should_use_shared_separation,
            )
        except PreprocessError:
            if not use_shared_source:
                try:
                    os.unlink(window_path)
                except FileNotFoundError:
                    pass
            continue

        if not use_shared_source:
            try:
                os.unlink(window_path)
            except FileNotFoundError:
                pass

        cleanup_dirs.extend(pp_dirs)
        speech_seconds = float(result.total_speech_seconds)
        profile_windows.append(
            ReferenceProfileWindow(
                index=window.index,
                start_seconds=window.start_seconds,
                duration_seconds=window.duration_seconds,
                speech_seconds=speech_seconds,
                weight=compute_profile_weight(speech_seconds, power=cfg.profile_weight_power),
                segments=result.segments,
            )
        )

    return profile_windows, cleanup_dirs, total_duration


async def persist_reference_embeddings(
    db: AsyncSession,
    *,
    asset_id: int,
    speaker_id: int,
    available_models: list[str],
    registry: EmbedderRegistry,
    profile_windows: list[ReferenceProfileWindow],
    overwrite: bool = False,
) -> dict[str, object]:
    """Persist one embedding row per retained profile window and model."""
    existing_stmt = select(Embedding.model_version).where(Embedding.audio_asset_id == asset_id)
    existing = set((await db.execute(existing_stmt)).scalars().all())

    target_models = list(available_models) if overwrite else [model_id for model_id in available_models if model_id not in existing]
    if overwrite and target_models:
        await repo.delete_embeddings_for_audio_asset(db, asset_id=asset_id, model_versions=target_models)

    created = 0
    failures: list[str] = []
    for model_id in target_models:
        try:
            embedder = registry.get(model_id)
            prepared: list[tuple[ReferenceProfileWindow, np.ndarray]] = []
            for window in profile_windows:
                vector = embed_segments(embedder, window.segments)
                prepared.append((window, vector))

            for window, vector in prepared:
                await repo.create_embedding(
                    db,
                    speaker_id=speaker_id,
                    audio_asset_id=asset_id,
                    vector=vector,
                    model_version=model_id,
                    window_index=window.index,
                    window_start_seconds=window.start_seconds,
                    window_duration_seconds=window.duration_seconds,
                    speech_seconds=window.speech_seconds,
                    weight=window.weight,
                )
                created += 1
        except Exception:
            failures.append(f"{model_id}: embedding failed")

    return {
        "created": created,
        "skipped_models": [model_id for model_id in available_models if model_id not in target_models],
        "failures": failures,
    }


def weighted_reference_embedding(rows: list[Embedding]) -> np.ndarray:
    vectors = [np.array(row.vector) for row in rows]
    weights = [float(row.weight or 1.0) for row in rows]
    return weighted_average_embeddings(vectors, weights=weights)


def _asset_reference_embeddings(rows: list[Embedding]) -> list[np.ndarray]:
    """Collapse multiple windows from one asset into one equal-weight prototype."""
    grouped: dict[object, list[Embedding]] = defaultdict(list)
    for index, row in enumerate(rows):
        asset_id = getattr(row, "audio_asset_id", None)
        row_id = getattr(row, "id", index)
        grouped[("asset", asset_id) if asset_id is not None else ("row", row_id)].append(row)

    prototypes: list[np.ndarray] = []
    for asset_rows in grouped.values():
        prototypes.append(weighted_reference_embedding(asset_rows))
    return prototypes


def compare_reference_profiles(
    rows_a: list[Embedding],
    rows_b: list[Embedding],
) -> ReferenceProfileComparison:
    """Compare profiles by bidirectional asset coverage instead of one centroid.

    Each audio asset contributes one prototype regardless of how many windows
    it produced.  The score is the mean of each side's best cross-profile
    asset match, which is more robust to mixed speaking/singing material than
    collapsing every window into a single centroid.
    """
    assets_a = _asset_reference_embeddings(rows_a)
    assets_b = _asset_reference_embeddings(rows_b)
    if not assets_a or not assets_b:
        raise ValueError("Both reference profiles must contain embeddings")

    normalized_a = np.stack(
        [vector / (np.linalg.norm(vector) or 1.0) for vector in assets_a],
    )
    normalized_b = np.stack(
        [vector / (np.linalg.norm(vector) or 1.0) for vector in assets_b],
    )
    cross_scores = normalized_a @ normalized_b.T
    coverage_score = float(
        (np.mean(np.max(cross_scores, axis=1)) + np.mean(np.max(cross_scores, axis=0)))
        / 2.0
    )

    centroid_a = weighted_average_embeddings(assets_a)
    centroid_b = weighted_average_embeddings(assets_b)
    centroid_score = float(
        np.dot(centroid_a, centroid_b)
        / ((np.linalg.norm(centroid_a) or 1.0) * (np.linalg.norm(centroid_b) or 1.0))
    )
    return ReferenceProfileComparison(
        score=coverage_score,
        coverage_score=coverage_score,
        centroid_score=centroid_score,
        asset_count_a=len(assets_a),
        asset_count_b=len(assets_b),
    )
