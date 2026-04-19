from __future__ import annotations

from minio import Minio
from minio.error import S3Error
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import repository as repo


def is_missing_object_error(exc: S3Error) -> bool:
    return exc.code in {"NoSuchKey", "NoSuchObject"}


def delete_object_if_exists(minio_client: Minio, object_name: str) -> bool:
    try:
        minio_client.remove_object(settings.minio_bucket, object_name)
        return True
    except S3Error as exc:
        if is_missing_object_error(exc):
            return False
        raise


def object_exists(minio_client: Minio, object_name: str) -> bool:
    try:
        minio_client.stat_object(settings.minio_bucket, object_name)
        return True
    except S3Error as exc:
        if is_missing_object_error(exc):
            return False
        raise


def list_prefix_object_names(minio_client: Minio, prefix: str) -> set[str]:
    return {
        obj.object_name
        for obj in minio_client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True)
    }


async def run_housekeep(db: AsyncSession, minio_client: Minio) -> dict:
    assets = await repo.list_audio_assets(db)

    deleted_db_assets = 0
    deleted_embeddings = 0
    deleted_minio_objects = 0
    deleted_missing_object_assets = 0
    deleted_unassigned_assets = 0
    live_storage_keys: set[str] = set()

    for asset in assets:
        if asset.speaker_id is None:
            deleted_embeddings += await repo.count_embeddings_for_audio_asset(db, asset.id)
            if delete_object_if_exists(minio_client, asset.storage_key):
                deleted_minio_objects += 1
            await repo.delete_audio_asset(db, asset.id)
            deleted_db_assets += 1
            deleted_unassigned_assets += 1
            continue

        if object_exists(minio_client, asset.storage_key):
            live_storage_keys.add(asset.storage_key)
            continue

        deleted_embeddings += await repo.count_embeddings_for_audio_asset(db, asset.id)
        await repo.delete_audio_asset(db, asset.id)
        deleted_db_assets += 1
        deleted_missing_object_assets += 1

    for object_name in list_prefix_object_names(minio_client, prefix="speakers/"):
        if object_name in live_storage_keys:
            continue
        if delete_object_if_exists(minio_client, object_name):
            deleted_minio_objects += 1

    await db.commit()

    return {
        "deleted_db_assets": deleted_db_assets,
        "deleted_embeddings": deleted_embeddings,
        "deleted_minio_objects": deleted_minio_objects,
        "deleted_missing_object_assets": deleted_missing_object_assets,
        "deleted_unassigned_assets": deleted_unassigned_assets,
        "kept_assets": len(live_storage_keys),
    }


async def preview_speaker_delete(
    db: AsyncSession,
    minio_client: Minio,
    speaker_id: int,
) -> dict | None:
    speaker = await repo.get_speaker(db, speaker_id)
    if not speaker:
        return None

    assets = await repo.get_speaker_audio_assets(db, speaker_id)
    storage_keys = {asset.storage_key for asset in assets}
    object_names = list_prefix_object_names(minio_client, prefix=f"speakers/{speaker_id}/")
    for object_name in storage_keys:
        if object_exists(minio_client, object_name):
            object_names.add(object_name)

    return {
        "speaker_id": speaker.id,
        "speaker_name": speaker.name,
        "audio_asset_count": len(assets),
        "embedding_count": await repo.count_embeddings_for_audio_assets(db, [asset.id for asset in assets]),
        "minio_object_count": len(object_names),
    }


async def preview_audio_asset_delete(
    db: AsyncSession,
    minio_client: Minio,
    speaker_id: int,
    asset_id: int,
) -> dict | None:
    asset = await repo.get_speaker_audio_asset(db, speaker_id, asset_id)
    if not asset:
        return None

    return {
        "speaker_id": speaker_id,
        "audio_asset_id": asset.id,
        "original_filename": asset.original_filename,
        "audio_asset_count": 1,
        "embedding_count": await repo.count_embeddings_for_audio_asset(db, asset.id),
        "minio_object_count": 1 if object_exists(minio_client, asset.storage_key) else 0,
    }