"""MinIO object-storage client."""

from minio import Minio
from app.config import settings


def init_minio() -> Minio:
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)
    return client


def upload_file(client: Minio, object_name: str, file_path: str, content_type: str = "audio/wav") -> str:
    client.fput_object(
        settings.minio_bucket,
        object_name,
        file_path,
        content_type=content_type,
    )
    return object_name


def delete_objects_by_prefix(client: Minio, prefix: str) -> None:
    """Delete all objects whose key starts with *prefix*."""
    from minio.deleteobjects import DeleteObject
    objects = client.list_objects(settings.minio_bucket, prefix=prefix, recursive=True)
    delete_list = [DeleteObject(obj.object_name) for obj in objects]
    if delete_list:
        errors = list(client.remove_objects(settings.minio_bucket, iter(delete_list)))
        if errors:
            import logging
            logging.getLogger(__name__).warning("MinIO delete errors: %s", errors)
