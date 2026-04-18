"""1:1 speaker verification endpoint."""

import os
import shutil
import tempfile
import time
import uuid

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_embedder_registry, get_calibrator_registry, get_preprocessor
from app.config import settings
from app.core.audio import validate_extension
from app.core.calibration import CalibratorRegistry
from app.core.embedder import EmbedderRegistry, embed_segments
from app.core.preprocessing import AudioPreprocessor, PreprocessError
from app.core.voice_features import compare_voice_characteristics
from app.db import repository as repo

router = APIRouter()


@router.post("/verify")
async def verify(
    audio_a: UploadFile = File(...),
    audio_b: UploadFile | None = File(None),
    speaker_id: int | None = Form(None),
    model: str = Form(""),
    separate_vocals: bool | None = Form(None),
    denoise: bool | None = Form(None),
    include_timings: bool = Form(False),
    enable_fast_return: bool = Form(False),
    fast_return_margin: float = Form(0.18),
    db: AsyncSession = Depends(get_db),
    registry: EmbedderRegistry = Depends(get_embedder_registry),
    calibrators: CalibratorRegistry = Depends(get_calibrator_registry),
    preprocessor: AudioPreprocessor = Depends(get_preprocessor),
):
    """Compare two audio clips, or one clip against an enrolled speaker."""
    if audio_b is None and speaker_id is None:
        raise HTTPException(400, "Provide either audio_b or speaker_id")

    model_id = model.strip() or settings.default_model
    if model_id not in registry.available_ids:
        raise HTTPException(400, f"Unknown or disabled model: {model_id}")

    embedder = registry.get(model_id)
    calibrator = calibrators.get(model_id)
    model_cfg = settings.get_model(model_id)
    threshold = model_cfg.verify_threshold if model_cfg else settings.verify_threshold

    for f in [audio_a, audio_b]:
        if f and (not f.filename or not validate_extension(f.filename)):
            raise HTTPException(400, "Unsupported audio format")

    tmp_dir = tempfile.mkdtemp()
    cleanup_dirs: list[str] = []
    request_started = time.perf_counter()
    try:
        use_separation = settings.preprocess_separate_vocals if separate_vocals is None else separate_vocals
        use_denoise = settings.preprocess_denoise if denoise is None else denoise
        fast_return_margin = max(0.0, min(float(fast_return_margin), 1.0))

        ext_a = os.path.splitext(audio_a.filename or "audio.wav")[1] or ".wav"
        path_a = os.path.join(tmp_dir, f"a_{uuid.uuid4().hex[:8]}{ext_a}")
        with open(path_a, "wb") as f:
            f.write(await audio_a.read())

        path_b = None
        if audio_b is not None:
            ext_b = os.path.splitext(audio_b.filename or "audio.wav")[1] or ".wav"
            path_b = os.path.join(tmp_dir, f"b_{uuid.uuid4().hex[:8]}{ext_b}")
            with open(path_b, "wb") as f:
                f.write(await audio_b.read())

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

        if enable_fast_return and path_b is not None:
            quick_timings: dict[str, dict | float] = {}
            quick_started = time.perf_counter()
            try:
                res_a_quick, dirs_a_quick = preprocessor.process(
                    path_a,
                    separate_vocals=False,
                    denoise=use_denoise,
                    collect_timings=include_timings,
                )
                cleanup_dirs.extend(dirs_a_quick)
                quick_timings["audio_a"] = res_a_quick.timings

                embed_started = time.perf_counter()
                emb_a_quick = embed_segments(embedder, res_a_quick.segments)
                quick_timings["embed_a"] = round(time.perf_counter() - embed_started, 4)

                res_b_quick, dirs_b_quick = preprocessor.process(
                    path_b,
                    separate_vocals=False,
                    denoise=use_denoise,
                    collect_timings=include_timings,
                )
                cleanup_dirs.extend(dirs_b_quick)
                quick_timings["audio_b"] = res_b_quick.timings

                embed_started = time.perf_counter()
                emb_b_quick = embed_segments(embedder, res_b_quick.segments)
                quick_timings["embed_b"] = round(time.perf_counter() - embed_started, 4)

                score_quick = embedder.similarity(emb_a_quick, emb_b_quick)
                probability_quick = calibrator.calibrate(score_quick)
                margin_from_threshold = abs(score_quick - threshold)
                quick_timings["total"] = round(time.perf_counter() - quick_started, 4)
                quick_timings["request_total"] = round(time.perf_counter() - request_started, 4)
                quick_voice_characteristics = compare_voice_characteristics(
                    res_a_quick.analysis_waveform,
                    res_b_quick.analysis_waveform,
                )

                if (not use_separation) or margin_from_threshold >= fast_return_margin:
                    return build_response(
                        score=score_quick,
                        probability=probability_quick,
                        strategy="fast-profile" if (not use_separation) else "fast-return",
                        preprocess_options={"separate_vocals": False, "denoise": use_denoise},
                        elapsed_seconds=quick_timings["request_total"],
                        timings=quick_timings,
                        margin_from_threshold=margin_from_threshold,
                        voice_characteristics=quick_voice_characteristics,
                    )
            except PreprocessError:
                quick_timings["fast_return_fallback"] = 1.0

        preprocess_started = time.perf_counter()
        try:
            res_a, dirs_a = preprocessor.process(
                path_a,
                separate_vocals=use_separation,
                denoise=use_denoise,
                collect_timings=include_timings,
            )
        except PreprocessError as exc:
            raise HTTPException(422, f"audio_a: {exc}")
        cleanup_dirs.extend(dirs_a)
        preprocess_a_wall = round(time.perf_counter() - preprocess_started, 4)

        embed_started = time.perf_counter()
        emb_a = embed_segments(embedder, res_a.segments)
        embed_a_time = round(time.perf_counter() - embed_started, 4)

        timings: dict[str, dict | float] = {
            "audio_a": res_a.timings,
            "audio_a_wall": preprocess_a_wall,
            "embed_a": embed_a_time,
        }

        if path_b is not None:
            preprocess_started = time.perf_counter()
            try:
                res_b, dirs_b = preprocessor.process(
                    path_b,
                    separate_vocals=use_separation,
                    denoise=use_denoise,
                    collect_timings=include_timings,
                )
            except PreprocessError as exc:
                raise HTTPException(422, f"audio_b: {exc}")
            cleanup_dirs.extend(dirs_b)
            timings["audio_b"] = res_b.timings
            timings["audio_b_wall"] = round(time.perf_counter() - preprocess_started, 4)

            embed_started = time.perf_counter()
            emb_b = embed_segments(embedder, res_b.segments)
            timings["embed_b"] = round(time.perf_counter() - embed_started, 4)
        else:
            enrolled = await repo.get_speaker_embeddings(db, speaker_id)
            if not enrolled:
                raise HTTPException(404, "Speaker not found or has no embeddings")
            same_model = [e for e in enrolled if e.model_version == model_id]
            if not same_model:
                same_model = enrolled
            vectors = [np.array(e.vector) for e in same_model]
            emb_b = np.mean(vectors, axis=0)
            timings["speaker_lookup"] = 0.0

        score_started = time.perf_counter()
        score = embedder.similarity(emb_a, emb_b)
        probability = calibrator.calibrate(score)
        timings["score"] = round(time.perf_counter() - score_started, 4)
        timings["total"] = round(time.perf_counter() - request_started, 4)

        voice_characteristics = None
        if path_b is not None:
            voice_characteristics = compare_voice_characteristics(
                res_a.analysis_waveform,
                res_b.analysis_waveform,
            )

        return build_response(
            score=score,
            probability=probability,
            strategy="full",
            preprocess_options={"separate_vocals": use_separation, "denoise": use_denoise},
            elapsed_seconds=timings["total"],
            timings=timings,
            margin_from_threshold=abs(score - threshold),
            voice_characteristics=voice_characteristics,
        )

    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for d in cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)
