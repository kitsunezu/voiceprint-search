"""Shared verify pipeline for sync and async execution paths."""

from __future__ import annotations

import asyncio
import shutil
import time
from collections.abc import Awaitable, Callable

import numpy as np
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calibration import ScoreCalibrator
from app.core.embedder import BaseEmbedder, embed_segments
from app.core.preprocessing import AudioPreprocessor, PreprocessError
from app.core.voice_features import compare_voice_characteristics
from app.db import repository as repo

ProgressHook = Callable[[str, int], None]
SpeakerEmbeddingLoader = Callable[[int], Awaitable[np.ndarray]]


async def load_speaker_reference_embedding(
    db: AsyncSession,
    speaker_id: int,
    model_id: str,
) -> np.ndarray:
    """Return the reference embedding for an enrolled speaker."""
    enrolled = await repo.get_speaker_embeddings(db, speaker_id)
    if not enrolled:
        raise HTTPException(404, "Speaker not found or has no embeddings")

    same_model = [e for e in enrolled if e.model_version == model_id]
    if not same_model:
        same_model = enrolled

    vectors = [np.array(e.vector) for e in same_model]
    return np.mean(vectors, axis=0)


async def run_verify_pipeline(
    *,
    path_a: str,
    path_b: str | None,
    speaker_id: int | None,
    model_id: str,
    threshold: float,
    separate_vocals: bool,
    denoise: bool,
    include_timings: bool,
    enable_fast_return: bool,
    fast_return_margin: float,
    embedder: BaseEmbedder,
    calibrator: ScoreCalibrator,
    preprocessor: AudioPreprocessor,
    load_speaker_embedding: SpeakerEmbeddingLoader | None = None,
    progress_hook: ProgressHook | None = None,
) -> dict:
    """Run the full verify flow and return the API response payload."""
    if path_b is None and speaker_id is None:
        raise HTTPException(400, "Provide either audio_b or speaker_id")

    fast_return_margin = max(0.0, min(float(fast_return_margin), 1.0))

    cleanup_dirs: list[str] = []
    request_started = time.perf_counter()

    def report(stage: str, progress: int) -> None:
        if progress_hook is not None:
            progress_hook(stage, progress)

    def build_response(
        *,
        score: float,
        probability: float,
        strategy: str,
        preprocess_options: dict[str, bool],
        elapsed_seconds: float,
        timings: dict | None = None,
        margin_from_threshold: float | None = None,
        voice_characteristics: dict | None = None,
    ) -> dict:
        response = {
            "score": round(score, 4),
            "probability": round(probability, 4),
            "is_same_speaker": score >= threshold,
            "threshold": threshold,
            "model_used": model_id,
            "strategy": strategy,
            "elapsed_seconds": round(elapsed_seconds, 4),
            "preprocess_options": preprocess_options,
        }
        if margin_from_threshold is not None:
            response["margin_from_threshold"] = round(margin_from_threshold, 4)
        if voice_characteristics is not None:
            response["voice_characteristics"] = voice_characteristics
        if include_timings and timings is not None:
            response["timings"] = timings
        return response

    try:
        if enable_fast_return and path_b is not None:
            quick_timings: dict[str, dict | float] = {}
            quick_started = time.perf_counter()
            try:
                report("preprocess_a", 12)
                res_a_quick, dirs_a_quick = await asyncio.to_thread(
                    preprocessor.process,
                    path_a,
                    separate_vocals=False,
                    denoise=denoise,
                    collect_timings=include_timings,
                )
                cleanup_dirs.extend(dirs_a_quick)
                quick_timings["audio_a"] = res_a_quick.timings

                report("embed_a", 24)
                embed_started = time.perf_counter()
                emb_a_quick = await asyncio.to_thread(embed_segments, embedder, res_a_quick.segments)
                quick_timings["embed_a"] = round(time.perf_counter() - embed_started, 4)

                report("preprocess_b", 36)
                res_b_quick, dirs_b_quick = await asyncio.to_thread(
                    preprocessor.process,
                    path_b,
                    separate_vocals=False,
                    denoise=denoise,
                    collect_timings=include_timings,
                )
                cleanup_dirs.extend(dirs_b_quick)
                quick_timings["audio_b"] = res_b_quick.timings

                report("embed_b", 48)
                embed_started = time.perf_counter()
                emb_b_quick = await asyncio.to_thread(embed_segments, embedder, res_b_quick.segments)
                quick_timings["embed_b"] = round(time.perf_counter() - embed_started, 4)

                report("score", 90)
                score_quick = embedder.similarity(emb_a_quick, emb_b_quick)
                probability_quick = calibrator.calibrate(score_quick)
                margin_from_threshold = abs(score_quick - threshold)
                quick_timings["total"] = round(time.perf_counter() - quick_started, 4)
                quick_timings["request_total"] = round(time.perf_counter() - request_started, 4)

                quick_voice_characteristics = compare_voice_characteristics(
                    res_a_quick.analysis_waveform,
                    res_b_quick.analysis_waveform,
                )

                if (not separate_vocals) or margin_from_threshold >= fast_return_margin:
                    report("done", 100)
                    return build_response(
                        score=score_quick,
                        probability=probability_quick,
                        strategy="fast-profile" if (not separate_vocals) else "fast-return",
                        preprocess_options={"separate_vocals": False, "denoise": denoise},
                        elapsed_seconds=quick_timings["request_total"],
                        timings=quick_timings,
                        margin_from_threshold=margin_from_threshold,
                        voice_characteristics=quick_voice_characteristics,
                    )
            except PreprocessError:
                quick_timings["fast_return_fallback"] = 1.0

        report("preprocess_a", 18)
        preprocess_started = time.perf_counter()
        try:
            res_a, dirs_a = await asyncio.to_thread(
                preprocessor.process,
                path_a,
                separate_vocals=separate_vocals,
                denoise=denoise,
                collect_timings=include_timings,
            )
        except PreprocessError as exc:
            raise HTTPException(422, f"audio_a: {exc}")
        cleanup_dirs.extend(dirs_a)
        preprocess_a_wall = round(time.perf_counter() - preprocess_started, 4)

        report("embed_a", 32)
        embed_started = time.perf_counter()
        emb_a = await asyncio.to_thread(embed_segments, embedder, res_a.segments)
        embed_a_time = round(time.perf_counter() - embed_started, 4)

        timings: dict[str, dict | float] = {
            "audio_a": res_a.timings,
            "audio_a_wall": preprocess_a_wall,
            "embed_a": embed_a_time,
        }

        res_b = None
        if path_b is not None:
            report("preprocess_b", 52)
            preprocess_started = time.perf_counter()
            try:
                res_b, dirs_b = await asyncio.to_thread(
                    preprocessor.process,
                    path_b,
                    separate_vocals=separate_vocals,
                    denoise=denoise,
                    collect_timings=include_timings,
                )
            except PreprocessError as exc:
                raise HTTPException(422, f"audio_b: {exc}")
            cleanup_dirs.extend(dirs_b)
            timings["audio_b"] = res_b.timings
            timings["audio_b_wall"] = round(time.perf_counter() - preprocess_started, 4)

            report("embed_b", 72)
            embed_started = time.perf_counter()
            emb_b = await asyncio.to_thread(embed_segments, embedder, res_b.segments)
            timings["embed_b"] = round(time.perf_counter() - embed_started, 4)
        else:
            if speaker_id is None:
                raise HTTPException(400, "Provide either audio_b or speaker_id")
            if load_speaker_embedding is None:
                raise HTTPException(500, "Speaker embedding loader is not configured")

            report("speaker_lookup", 62)
            lookup_started = time.perf_counter()
            emb_b = await load_speaker_embedding(speaker_id)
            timings["speaker_lookup"] = round(time.perf_counter() - lookup_started, 4)

        report("score", 90)
        score_started = time.perf_counter()
        score = embedder.similarity(emb_a, emb_b)
        probability = calibrator.calibrate(score)
        timings["score"] = round(time.perf_counter() - score_started, 4)
        timings["total"] = round(time.perf_counter() - request_started, 4)

        voice_characteristics = None
        if res_b is not None:
            voice_characteristics = compare_voice_characteristics(
                res_a.analysis_waveform,
                res_b.analysis_waveform,
            )

        report("done", 100)
        return build_response(
            score=score,
            probability=probability,
            strategy="full",
            preprocess_options={"separate_vocals": separate_vocals, "denoise": denoise},
            elapsed_seconds=timings["total"],
            timings=timings,
            margin_from_threshold=abs(score - threshold),
            voice_characteristics=voice_characteristics,
        )

    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        for cleanup_dir in cleanup_dirs:
            shutil.rmtree(cleanup_dir, ignore_errors=True)
