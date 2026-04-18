"""Health check endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_embedder
from app.core.embedder import SpeakerEmbedder

router = APIRouter()


@router.get("/health")
async def health(
    db: AsyncSession = Depends(get_db),
    embedder: SpeakerEmbedder = Depends(get_embedder),
):
    db_ok = False
    try:
        await db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass

    return {
        "status": "ok" if db_ok else "degraded",
        "model_loaded": embedder.model is not None,
        "db_connected": db_ok,
    }
