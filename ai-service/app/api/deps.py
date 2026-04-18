"""FastAPI dependency injection helpers."""

from typing import AsyncGenerator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedder import BaseEmbedder, EmbedderRegistry
from app.core.vad import VoiceActivityDetector
from app.core.separator import VocalSeparator
from app.core.calibration import ScoreCalibrator, CalibratorRegistry
from app.core.preprocessing import AudioPreprocessor
from minio import Minio


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.db() as session:
        yield session


def get_embedder(request: Request) -> BaseEmbedder:
    """Return the default embedder (backward compat)."""
    return request.app.state.embedder


def get_embedder_registry(request: Request) -> EmbedderRegistry:
    return request.app.state.embedder_registry


def get_vad(request: Request) -> VoiceActivityDetector:
    return request.app.state.vad


def get_calibrator(request: Request) -> ScoreCalibrator:
    """Return the default calibrator (backward compat)."""
    return request.app.state.calibrator


def get_calibrator_registry(request: Request) -> CalibratorRegistry:
    return request.app.state.calibrator_registry


def get_minio(request: Request) -> Minio:
    return request.app.state.minio


def get_separator(request: Request) -> VocalSeparator:
    return request.app.state.separator


def get_preprocessor(request: Request) -> AudioPreprocessor:
    return request.app.state.preprocessor
