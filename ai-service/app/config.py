from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings


class ModelConfig(BaseModel):
    """Configuration for a single speaker-embedding model."""
    id: str
    label: str                      # human-readable name shown in frontend
    source: str                     # model hub path or package identifier
    backend: str                    # "speechbrain" | "resemblyzer" | "pyannote"
    embedding_dim: int
    cache_dir: str                  # where weights are cached inside the container
    calibration_weight: float = 10.0
    calibration_bias: float = -3.5
    verify_threshold: float = 0.60
    enabled: bool = True
    hf_token_env: str | None = None  # env var name for gated models (e.g. pyannote)


class SeparatorProfile(BaseModel):
    """Configuration for a vocal-separation profile."""

    id: str
    label: str
    backend: str                  # "demucs" | "audio-separator"
    model: str                   # model id / filename understood by the backend


# ── Built-in model definitions ────────────────────────────────────────────

ECAPA_MODEL = ModelConfig(
    id="ecapa-tdnn-v1",
    label="ECAPA-TDNN (SpeechBrain)",
    source="speechbrain/spkrec-ecapa-voxceleb",
    backend="speechbrain",
    embedding_dim=192,
    cache_dir="/models/ecapa-tdnn",
    calibration_weight=10.0,
    calibration_bias=-3.5,
    verify_threshold=0.60,
)

RESEMBLYZER_MODEL = ModelConfig(
    id="resemblyzer-v1",
    label="Resemblyzer (d-vector)",
    source="default",
    backend="resemblyzer",
    embedding_dim=256,
    cache_dir="/models/resemblyzer",
    calibration_weight=8.0,
    calibration_bias=-2.8,
    verify_threshold=0.70,
    enabled=False,
)

PYANNOTE_MODEL = ModelConfig(
    id="pyannote-v1",
    label="Pyannote (TDNN)",
    source="pyannote/embedding",
    backend="pyannote",
    embedding_dim=512,
    cache_dir="/models/pyannote",
    calibration_weight=6.0,
    calibration_bias=-2.0,
    verify_threshold=0.50,
    hf_token_env="HF_TOKEN",
)

DEFAULT_MODELS: list[ModelConfig] = [ECAPA_MODEL, RESEMBLYZER_MODEL]

DEMUCS_SEPARATOR = SeparatorProfile(
    id="demucs",
    label="Demucs HT",
    backend="demucs",
    model="htdemucs",
)

MDX_SEPARATOR = SeparatorProfile(
    id="mdx",
    label="UVR MDX-Net Kara",
    backend="audio-separator",
    model="UVR_MDXNET_KARA_2.onnx",
)

ROFORMER_SEPARATOR = SeparatorProfile(
    id="roformer",
    label="BS Roformer Viperx 1297",
    backend="audio-separator",
    model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
)

DEFAULT_SEPARATOR_PROFILES: list[SeparatorProfile] = [
    DEMUCS_SEPARATOR,
    MDX_SEPARATOR,
    ROFORMER_SEPARATOR,
]


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://voiceprint:voiceprint@localhost:5432/voiceprint"
    redis_url: str = "redis://localhost:6379/0"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "voiceprint-audio"
    minio_secure: bool = False
    minio_connect_timeout_seconds: float = 10.0
    minio_read_timeout_seconds: float = 120.0

    model_cache_dir: str = "/models"

    # Legacy single-model settings kept for backward compat
    embedding_model: str = "speechbrain/spkrec-ecapa-voxceleb"
    embedding_dim: int = 192

    # Score calibration defaults (pre-tuned on VoxCeleb)
    calibration_weight: float = 10.0
    calibration_bias: float = -3.5
    verify_threshold: float = 0.60

    # Default model used when caller does not specify one
    default_model: str = "ecapa-tdnn-v1"

    # Comma-separated list of model IDs to enable (empty = all built-in models flagged enabled)
    enabled_models: str = ""

    # ── Audio preprocessing pipeline ──────────────────────────────────────
    # All enroll / verify / search requests go through this mandatory pipeline.
    preprocess_separate_vocals: bool = True   # always run Demucs vocal separation
    preprocess_denoise: bool = True           # always run CPU-first noise reduction
    preprocess_normalize_max_seconds: int = 240  # max post-separation audio window decoded before downstream steps
    preprocess_min_speech_seconds: float = 3.0   # minimum usable speech after VAD
    preprocess_max_speech_seconds: float = 180.0  # max speech fed to embedder
    preprocess_segment_length_seconds: float = 6.0  # fixed-length window for long speech
    preprocess_segment_step_seconds: float = 3.0    # hop between windows (overlap = seg-step)
    preprocess_short_repeat: bool = True      # repeat-pad speech shorter than min to reach min
    preprocess_reject_no_speech: bool = True  # raise error when no speech detected at all

    # ── Vocal separation ──────────────────────────────────────────────────
    separator_profile: str = "demucs"                 # demucs | mdx | roformer
    separator_model_override: str = ""                # explicit backend model filename/id
    separator_model_dir: str = "/models/separators"   # persistent model cache for separators
    separator_cache_dir: str = "/tmp/voiceprint-separator-cache"
    separator_cache_enabled: bool = True
    separator_max_seconds: int = 240
    separator_timeout_seconds: int = 180

    # ── Search aggregation ────────────────────────────────────────────────
    search_strategy: str = "hybrid"          # best | centroid | hybrid
    search_hybrid_best_weight: float = 0.7
    search_hybrid_centroid_weight: float = 0.3

    # Upload limits
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    allowed_audio_types: list[str] = [
        "audio/mpeg", "audio/wav", "audio/x-wav", "audio/flac",
        "audio/ogg", "audio/mp4", "audio/webm", "audio/aac",
    ]

    # ── Observability ─────────────────────────────────────────────────────
    # Set OTEL_EXPORTER_OTLP_ENDPOINT to enable SigNoz / OTEL export.
    # Leave empty to run without any telemetry (local dev default).
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "voiceprint-ai-service"

    # ── Housekeeping ──────────────────────────────────────────────────────
    housekeep_enabled: bool = True
    housekeep_interval_seconds: int = 3600

    class Config:
        env_file = ".env"

    def get_enabled_models(self) -> list[ModelConfig]:
        """Return the list of enabled ModelConfig objects."""
        if self.enabled_models.strip():
            ids = {mid.strip() for mid in self.enabled_models.split(",")}
            return [m for m in DEFAULT_MODELS if m.id in ids]
        return [m for m in DEFAULT_MODELS if m.enabled]

    def get_model(self, model_id: str) -> ModelConfig | None:
        for m in self.get_enabled_models():
            if m.id == model_id:
                return m
        return None

    def get_separator_profile(
        self,
        profile_id: str | None = None,
        model_override: str | None = None,
    ) -> SeparatorProfile:
        selected_id = (profile_id or self.separator_profile).strip().lower()
        selected = next(
            (profile for profile in DEFAULT_SEPARATOR_PROFILES if profile.id == selected_id),
            DEMUCS_SEPARATOR,
        )
        override = (model_override if model_override is not None else self.separator_model_override).strip()
        if override:
            return selected.model_copy(update={"model": override})
        return selected


settings = Settings()
