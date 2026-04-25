"""Speaker embedding — base protocol, SpeechBrain adapter, and model registry."""

from __future__ import annotations

import logging
import os
from typing import Protocol

import numpy as np
import torch

from app.config import ModelConfig

logger = logging.getLogger(__name__)


# ── Base protocol ─────────────────────────────────────────────────────────

class BaseEmbedder(Protocol):
    """Interface every speaker-embedding backend must implement."""

    model_id: str
    embedding_dim: int

    def embed(self, waveform: np.ndarray, sample_rate: int = 16_000) -> np.ndarray: ...

    def similarity(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float: ...


def cosine_similarity(emb_a: np.ndarray, emb_b: np.ndarray) -> float:
    """Cosine similarity between two vectors.  Returns value in [-1, 1]."""
    norm_a = np.linalg.norm(emb_a)
    norm_b = np.linalg.norm(emb_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(emb_a, emb_b) / (norm_a * norm_b))


def weighted_average_embeddings(
    vectors: list[np.ndarray],
    *,
    weights: list[float] | None = None,
) -> np.ndarray:
    """Average embeddings and keep the result on the unit hypersphere."""
    if not vectors:
        raise ValueError("At least one embedding vector is required")
    if len(vectors) == 1:
        return vectors[0]

    if weights is None:
        mean = np.mean(vectors, axis=0)
    else:
        sanitized = np.array([max(float(weight), 0.0) for weight in weights], dtype=np.float32)
        if float(np.sum(sanitized)) <= 0:
            mean = np.mean(vectors, axis=0)
        else:
            mean = np.average(vectors, axis=0, weights=sanitized)

    norm = np.linalg.norm(mean)
    if norm > 0:
        mean = mean / norm
    return mean


def embed_segments(
    embedder: "BaseEmbedder",
    segments: list[np.ndarray],
    sample_rate: int = 16_000,
) -> np.ndarray:
    """Embed each segment independently and return the L2-normalised mean.

    For a single segment this is equivalent to ``embedder.embed(segment)``.
    For multiple segments (long audio split into windows) the per-segment
    embeddings are averaged and re-normalised so the result lives on the
    unit hypersphere — compatible with cosine-similarity scoring.
    """
    if len(segments) == 1:
        return embedder.embed(segments[0], sample_rate)

    vectors = [embedder.embed(seg, sample_rate) for seg in segments]
    return weighted_average_embeddings(vectors)


# ── SpeechBrain ECAPA-TDNN ────────────────────────────────────────────────

class SpeechBrainEmbedder:
    """Produce fixed-length speaker embeddings via SpeechBrain."""

    def __init__(self, cfg: ModelConfig):
        from speechbrain.inference.speaker import EncoderClassifier

        self.model_id = cfg.id
        self.embedding_dim = cfg.embedding_dim
        self.model = EncoderClassifier.from_hparams(
            source=cfg.source,
            savedir=cfg.cache_dir,
            run_opts={"device": "cpu"},
        )

    def embed(self, waveform: np.ndarray, sample_rate: int = 16_000) -> np.ndarray:
        signal = torch.tensor(waveform, dtype=torch.float32).unsqueeze(0)
        with torch.no_grad():
            embedding = self.model.encode_batch(signal)
        return embedding.squeeze().cpu().numpy()

    def similarity(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        return cosine_similarity(emb_a, emb_b)


# ── Resemblyzer (d-vector / GE2E) ────────────────────────────────────────

class ResemblyzerEmbedder:
    """256-dim d-vector embeddings via Resemblyzer."""

    def __init__(self, cfg: ModelConfig):
        from resemblyzer import VoiceEncoder

        self.model_id = cfg.id
        self.embedding_dim = cfg.embedding_dim
        self.encoder = VoiceEncoder(device="cpu")

    def embed(self, waveform: np.ndarray, sample_rate: int = 16_000) -> np.ndarray:
        from resemblyzer import preprocess_wav

        # Resemblyzer expects float64 array at 16 kHz
        wav = preprocess_wav(waveform, source_sr=sample_rate)
        return self.encoder.embed_utterance(wav)

    def similarity(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        return cosine_similarity(emb_a, emb_b)


# ── Pyannote ──────────────────────────────────────────────────────────────

class PyannoteEmbedder:
    """512-dim embeddings via pyannote.audio."""

    def __init__(self, cfg: ModelConfig):
        from pyannote.audio import Inference as PyannoteInference

        self.model_id = cfg.id
        self.embedding_dim = cfg.embedding_dim

        hf_token = os.environ.get(cfg.hf_token_env or "", None) if cfg.hf_token_env else None
        init_kwargs: dict = {"window": "whole"}
        if hf_token:
            init_kwargs["token"] = hf_token
        self.inference = PyannoteInference(cfg.source, **init_kwargs)

    def embed(self, waveform: np.ndarray, sample_rate: int = 16_000) -> np.ndarray:
        import tempfile
        import scipy.io.wavfile as wavfile

        # pyannote expects a file path; write a temp WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            int16 = (waveform * 32767).astype(np.int16)
            wavfile.write(f.name, sample_rate, int16)
            path = f.name
        try:
            embedding = self.inference(path)
            return np.array(embedding).flatten()
        finally:
            os.unlink(path)

    def similarity(self, emb_a: np.ndarray, emb_b: np.ndarray) -> float:
        return cosine_similarity(emb_a, emb_b)


# ── Registry ──────────────────────────────────────────────────────────────

_BACKEND_MAP: dict[str, type] = {
    "speechbrain": SpeechBrainEmbedder,
    "resemblyzer": ResemblyzerEmbedder,
    "pyannote": PyannoteEmbedder,
}


class EmbedderRegistry:
    """Lazy-loading registry that maps model IDs to embedder instances."""

    def __init__(self):
        self._instances: dict[str, BaseEmbedder] = {}
        self._configs: dict[str, ModelConfig] = {}

    def register(self, cfg: ModelConfig) -> None:
        self._configs[cfg.id] = cfg

    def get(self, model_id: str) -> BaseEmbedder:
        if model_id in self._instances:
            return self._instances[model_id]

        cfg = self._configs.get(model_id)
        if cfg is None:
            raise ValueError(f"Unknown model: {model_id}")

        cls = _BACKEND_MAP.get(cfg.backend)
        if cls is None:
            raise ValueError(f"Unknown backend: {cfg.backend}")

        logger.info("Loading model %s (backend=%s) …", model_id, cfg.backend)
        try:
            instance = cls(cfg)
        except Exception:
            logger.exception("Failed to load model %s", model_id)
            raise
        self._instances[model_id] = instance
        return instance

    def preload(self, model_id: str) -> None:
        """Eagerly load a model at startup."""
        self.get(model_id)

    @property
    def available_ids(self) -> list[str]:
        return list(self._configs.keys())

    @property
    def loaded_ids(self) -> list[str]:
        return list(self._instances.keys())


# ── Backward-compat alias used by existing imports ────────────────────────
SpeakerEmbedder = SpeechBrainEmbedder
