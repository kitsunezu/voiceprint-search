"""Reference-profile helpers for long-form enrollment assets."""

from __future__ import annotations

from dataclasses import dataclass
import logging
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


logger = logging.getLogger(__name__)


@dataclass
class ReferenceProfileWindow:
    index: int
    start_seconds: float
    duration_seconds: float
    speech_seconds: float
    weight: float
    segments: list[np.ndarray]


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

    should_use_shared_separation = cfg.preprocess_separate_vocals and (
        total_duration is None or total_duration <= float(cfg.separator_max_seconds)
    )

    if should_use_shared_separation:
        shared_source_path, sep_dir = preprocessor.separator.separate(raw_audio_path, max_duration_seconds=None)
        shared_cleanup_dirs.append(sep_dir)
    elif cfg.preprocess_separate_vocals:
        logger.info(
            "Skipping vocal separation for long reference asset duration=%.1fs (limit=%ss)",
            float(total_duration),
            int(cfg.separator_max_seconds),
        )

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
            result, pp_dirs = preprocessor.process(window_path, separate_vocals=False)
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