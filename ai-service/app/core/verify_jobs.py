"""Redis-backed state store for asynchronous verify jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from redis import Redis

from app.config import settings

VERIFY_JOB_TTL_SECONDS = 24 * 60 * 60
VERIFY_JOB_PREFIX = "voiceprint:verify-job:"

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return a singleton Redis client for API and worker processes."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def create_verify_job(redis_client: Redis, job_id: str) -> dict:
    now = _utcnow_iso()
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "eta_seconds": None,
        "created_at": now,
        "started_at": None,
        "updated_at": now,
        "finished_at": None,
        "error": None,
        "result": None,
    }
    _store_job(redis_client, job)
    return job


def get_verify_job(redis_client: Redis, job_id: str) -> dict | None:
    return _load_job(redis_client, job_id)


def mark_verify_job_running(
    redis_client: Redis,
    job_id: str,
    *,
    stage: str,
    progress: int,
) -> dict | None:
    return update_verify_job(
        redis_client,
        job_id,
        status="running",
        stage=stage,
        progress=progress,
    )


def update_verify_job_progress(
    redis_client: Redis,
    job_id: str,
    *,
    stage: str,
    progress: int,
) -> dict | None:
    return update_verify_job(
        redis_client,
        job_id,
        status="running",
        stage=stage,
        progress=progress,
    )


def complete_verify_job(redis_client: Redis, job_id: str, *, result: dict) -> dict | None:
    return update_verify_job(
        redis_client,
        job_id,
        status="succeeded",
        stage="done",
        progress=100,
        result=result,
        error=None,
    )


def fail_verify_job(redis_client: Redis, job_id: str, *, error: str) -> dict | None:
    return update_verify_job(
        redis_client,
        job_id,
        status="failed",
        stage="failed",
        progress=100,
        error=error,
    )


def update_verify_job(
    redis_client: Redis,
    job_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: int | None = None,
    result: dict | None = None,
    error: str | None = None,
) -> dict | None:
    job = _load_job(redis_client, job_id)
    if job is None:
        return None

    now = datetime.now(timezone.utc)

    if status is not None:
        job["status"] = status
    if stage is not None:
        job["stage"] = stage
    if progress is not None:
        job["progress"] = max(0, min(100, int(progress)))

    if job.get("status") == "running" and not job.get("started_at"):
        job["started_at"] = now.isoformat()

    if result is not None:
        job["result"] = result
    if error is not None:
        job["error"] = error

    if job.get("status") == "running":
        job["eta_seconds"] = _estimate_eta_seconds(job, now)
    elif job.get("status") == "succeeded":
        job["eta_seconds"] = 0
        job["finished_at"] = now.isoformat()
    elif job.get("status") == "failed":
        job["eta_seconds"] = None
        job["finished_at"] = now.isoformat()

    job["updated_at"] = now.isoformat()
    _store_job(redis_client, job)
    return job


def _estimate_eta_seconds(job: dict, now: datetime) -> int | None:
    progress = int(job.get("progress", 0) or 0)
    if progress <= 0 or progress >= 100:
        return None

    started_at_raw = job.get("started_at")
    if not isinstance(started_at_raw, str) or not started_at_raw:
        return None

    try:
        started_at = datetime.fromisoformat(started_at_raw)
    except ValueError:
        return None

    elapsed_seconds = max(0.0, (now - started_at).total_seconds())
    estimated_total = elapsed_seconds / (progress / 100.0)
    eta = int(round(max(0.0, estimated_total - elapsed_seconds)))
    return eta


def _job_key(job_id: str) -> str:
    return f"{VERIFY_JOB_PREFIX}{job_id}"


def _load_job(redis_client: Redis, job_id: str) -> dict | None:
    raw = redis_client.get(_job_key(job_id))
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _store_job(redis_client: Redis, job: dict) -> None:
    job_id = str(job.get("job_id", ""))
    if not job_id:
        raise ValueError("job_id is required")
    redis_client.set(_job_key(job_id), json.dumps(job), ex=VERIFY_JOB_TTL_SECONDS)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
