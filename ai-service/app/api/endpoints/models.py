"""Model listing endpoint — expose available embedding models to the frontend."""

import os

from fastapi import APIRouter, Depends

from app.api.deps import get_embedder_registry
from app.config import settings
from app.core.embedder import EmbedderRegistry

router = APIRouter()


def _model_available(hf_token_env: str | None) -> bool:
    """Return True if model can be instantiated (gated models need their token set)."""
    if not hf_token_env:
        return True
    return bool(os.environ.get(hf_token_env, "").strip())


@router.get("/models")
async def list_models(
    registry: EmbedderRegistry = Depends(get_embedder_registry),
):
    enabled = settings.get_enabled_models()
    return {
        "default_model": settings.default_model,
        "models": [
            {
                "id": m.id,
                "label": m.label,
                "backend": m.backend,
                "embedding_dim": m.embedding_dim,
                "loaded": m.id in registry.loaded_ids,
                "available": _model_available(m.hf_token_env),
            }
            for m in enabled
        ],
    }
