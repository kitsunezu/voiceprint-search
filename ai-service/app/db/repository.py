"""Database repository — speaker, embedding, and search operations."""

from __future__ import annotations

import numpy as np
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Speaker, AudioAsset, Embedding


async def create_speaker(session: AsyncSession, name: str, description: str | None = None) -> Speaker:
    speaker = Speaker(name=name, description=description)
    session.add(speaker)
    await session.flush()
    return speaker


async def get_speaker(session: AsyncSession, speaker_id: int) -> Speaker | None:
    return await session.get(Speaker, speaker_id)


async def list_speakers(session: AsyncSession) -> list[dict]:
    stmt = (
        select(
            Speaker.id,
            Speaker.name,
            Speaker.created_at,
            func.count(Embedding.id).label("embedding_count"),
        )
        .outerjoin(Embedding, Embedding.speaker_id == Speaker.id)
        .group_by(Speaker.id)
        .order_by(Speaker.id)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "embedding_count": r.embedding_count,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


async def create_audio_asset(
    session: AsyncSession,
    *,
    speaker_id: int | None,
    original_filename: str,
    storage_key: str,
    duration_seconds: float | None = None,
    sample_rate: int | None = None,
    has_speech: bool = True,
) -> AudioAsset:
    asset = AudioAsset(
        speaker_id=speaker_id,
        original_filename=original_filename,
        storage_key=storage_key,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        has_speech=has_speech,
    )
    session.add(asset)
    await session.flush()
    return asset


async def create_embedding(
    session: AsyncSession,
    *,
    speaker_id: int,
    audio_asset_id: int,
    vector: np.ndarray,
    model_version: str = "ecapa-tdnn-v1",
) -> Embedding:
    emb = Embedding(
        speaker_id=speaker_id,
        audio_asset_id=audio_asset_id,
        vector=vector.tolist(),
        model_version=model_version,
        embedding_dim=len(vector),
    )
    session.add(emb)
    await session.flush()
    return emb


async def get_speaker_embeddings(session: AsyncSession, speaker_id: int) -> list[Embedding]:
    stmt = select(Embedding).where(Embedding.speaker_id == speaker_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_speaker_audio_assets(session: AsyncSession, speaker_id: int) -> list[AudioAsset]:
    """Return all AudioAsset rows for a speaker."""
    stmt = select(AudioAsset).where(AudioAsset.speaker_id == speaker_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def update_speaker_name(session: AsyncSession, speaker_id: int, name: str) -> "Speaker | None":
    speaker = await session.get(Speaker, speaker_id)
    if not speaker:
        return None
    speaker.name = name
    await session.flush()
    return speaker


async def delete_speaker(session: AsyncSession, speaker_id: int) -> bool:
    speaker = await session.get(Speaker, speaker_id)
    if not speaker:
        return False
    await session.delete(speaker)
    await session.flush()
    return True


async def search_similar(
    session: AsyncSession,
    query_vector: np.ndarray,
    limit: int = 10,
    model_version: str | None = None,
    strategy: str = "best",
    hybrid_best_weight: float = 0.7,
    hybrid_centroid_weight: float = 0.3,
) -> list[dict]:
    """Find the closest enrolled speakers using pgvector cosine distance.

    Supports three aggregation modes:

    - ``best``: per-speaker best single embedding similarity.
    - ``centroid``: per-speaker centroid similarity.
    - ``hybrid``: weighted blend of ``best`` and ``centroid``.

    When *model_version* is provided, only embeddings from that model are
    searched — necessary for correct multi-model support.
    """
    vec_literal = "[" + ",".join(str(float(v)) for v in query_vector) + "]"
    strategy = strategy.strip().lower() or "best"
    if strategy not in {"best", "centroid", "hybrid"}:
        strategy = "best"

    model_filter = "WHERE e.model_version = :model_version" if model_version else ""

    if strategy == "best":
        stmt = text(f"""
        WITH ranked AS (
            SELECT
                e.speaker_id,
                s.name          AS speaker_name,
                1 - (e.vector <=> :vec) AS similarity,
                ROW_NUMBER() OVER (
                    PARTITION BY e.speaker_id
                    ORDER BY e.vector <=> :vec
                ) AS rn
            FROM embeddings e
            JOIN speakers s ON s.id = e.speaker_id
            {model_filter}
        )
        SELECT speaker_id, speaker_name, similarity
        FROM ranked
        WHERE rn = 1
        ORDER BY similarity DESC
        LIMIT :lim
        """)
    else:
        stmt = text(f"""
        WITH per_embedding AS (
            SELECT
                e.speaker_id,
                s.name AS speaker_name,
                1 - (e.vector <=> :vec) AS similarity,
                e.vector AS vector
            FROM embeddings e
            JOIN speakers s ON s.id = e.speaker_id
            {model_filter}
        ),
        best AS (
            SELECT
                speaker_id,
                speaker_name,
                MAX(similarity) AS best_similarity
            FROM per_embedding
            GROUP BY speaker_id, speaker_name
        ),
        centroids AS (
            SELECT
                e.speaker_id,
                s.name AS speaker_name,
                1 - (AVG(e.vector) <=> :vec) AS centroid_similarity
            FROM embeddings e
            JOIN speakers s ON s.id = e.speaker_id
            {model_filter}
            GROUP BY e.speaker_id, s.name
        )
        SELECT
            b.speaker_id,
            b.speaker_name,
            CASE
                WHEN :strategy = 'centroid' THEN c.centroid_similarity
                ELSE (:best_weight * b.best_similarity) + (:centroid_weight * c.centroid_similarity)
            END AS similarity,
            b.best_similarity,
            c.centroid_similarity
        FROM best b
        JOIN centroids c ON c.speaker_id = b.speaker_id
        ORDER BY similarity DESC
        LIMIT :lim
        """)

    params: dict = {
        "vec": vec_literal,
        "lim": limit,
        "strategy": strategy,
        "best_weight": hybrid_best_weight,
        "centroid_weight": hybrid_centroid_weight,
    }
    if model_version:
        params["model_version"] = model_version

    rows = (await session.execute(stmt, params)).all()

    return [
        {
            "speaker_id": r.speaker_id,
            "speaker_name": r.speaker_name,
            "score": float(r.similarity),
            "best_score": float(r.best_similarity) if hasattr(r, "best_similarity") and r.best_similarity is not None else None,
            "centroid_score": float(r.centroid_similarity) if hasattr(r, "centroid_similarity") and r.centroid_similarity is not None else None,
        }
        for r in rows
    ]
