"""1:N speaker search endpoint — find most similar voices in the database."""

import asyncio
import os
import shutil
import tempfile
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_embedder_registry, get_calibrator_registry, get_preprocessor
from app.config import settings
from app.core.audio import validate_extension
from app.core.calibration import CalibratorRegistry
from app.core.embedder import EmbedderRegistry, embed_segments
from app.core.preprocessing import AudioPreprocessor, PreprocessError
from app.db import repository as repo

router = APIRouter()


@router.post("/search")
async def search(
    audio: UploadFile = File(...),
    limit: int = Form(10),
    model: str = Form(""),
    separate_vocals: bool | None = Form(None),
    denoise: bool | None = Form(None),
    include_timings: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    registry: EmbedderRegistry = Depends(get_embedder_registry),
    calibrators: CalibratorRegistry = Depends(get_calibrator_registry),
    preprocessor: AudioPreprocessor = Depends(get_preprocessor),
):
    if not audio.filename or not validate_extension(audio.filename):
        raise HTTPException(400, "Unsupported audio format")

    if limit < 1 or limit > 100:
        raise HTTPException(400, "limit must be between 1 and 100")

    model_id = model.strip() or settings.default_model
    if model_id not in registry.available_ids:
        raise HTTPException(400, f"Unknown or disabled model: {model_id}")

    embedder = registry.get(model_id)
    calibrator = calibrators.get(model_id)

    tmp_dir = tempfile.mkdtemp()
    cleanup_dirs: list[str] = []
    request_started = time.perf_counter()
    try:
        ext = os.path.splitext(audio.filename or "audio.wav")[1] or ".wav"
        raw_path = os.path.join(tmp_dir, f"q_{uuid.uuid4().hex[:8]}{ext}")
        with open(raw_path, "wb") as f:
            f.write(await audio.read())

        # ── Mandatory preprocessing pipeline (offloaded to thread pool) ──
        try:
            preprocess_started = time.perf_counter()
            result, pp_dirs = await asyncio.to_thread(
                preprocessor.process,
                raw_path,
                separate_vocals=separate_vocals,
                denoise=denoise,
                collect_timings=include_timings,
            )
        except PreprocessError as exc:
            raise HTTPException(422, str(exc))
        cleanup_dirs.extend(pp_dirs)
        preprocess_wall = round(time.perf_counter() - preprocess_started, 4)

        embed_started = time.perf_counter()
        query_vec = await asyncio.to_thread(embed_segments, embedder, result.segments)
        embed_time = round(time.perf_counter() - embed_started, 4)

        search_started = time.perf_counter()
        matches = await repo.search_similar(
            db,
            query_vec,
            limit=limit,
            model_version=model_id,
            strategy=settings.search_strategy,
            hybrid_best_weight=settings.search_hybrid_best_weight,
            hybrid_centroid_weight=settings.search_hybrid_centroid_weight,
        )
        search_time = round(time.perf_counter() - search_started, 4)

        results = []
        calibrate_started = time.perf_counter()
        for rank, m in enumerate(matches, start=1):
            prob = calibrator.calibrate(m["score"])
            results.append({
                "speaker_id": m["speaker_id"],
                "speaker_name": m["speaker_name"],
                "score": round(m["score"], 4),
                "probability": round(prob, 4),
                "rank": rank,
                "best_score": round(m["best_score"], 4) if m.get("best_score") is not None else None,
                "centroid_score": round(m["centroid_score"], 4) if m.get("centroid_score") is not None else None,
            })
        calibrate_time = round(time.perf_counter() - calibrate_started, 4)

        response = {
            "results": results,
            "model_used": model_id,
            "elapsed_seconds": round(time.perf_counter() - request_started, 4),
            "preprocess_options": result.options,
            "search_strategy": settings.search_strategy,
        }
        if include_timings:
            response["timings"] = {
                "preprocess": result.timings,
                "preprocess_wall": preprocess_wall,
                "embed": embed_time,
                "search": search_time,
                "calibrate": calibrate_time,
                "total": round(time.perf_counter() - request_started, 4),
            }
        return response

    except ValueError as exc:
        raise HTTPException(422, str(exc))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        for d in cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)


@router.get("/speakers")
async def list_speakers(db: AsyncSession = Depends(get_db)):
    speakers = await repo.list_speakers(db)
    return {"speakers": speakers}
