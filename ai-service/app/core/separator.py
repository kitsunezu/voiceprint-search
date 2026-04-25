"""Vocal/music source separation with switchable separator profiles.

The public interface remains a simple ``VocalSeparator.separate()`` call, but
the implementation can now switch between multiple backends such as Demucs and
audio-separator based MDX / Roformer models.
"""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import logging
import os
from pathlib import Path
import signal
import shutil
import subprocess
import tempfile
import time
import uuid

from redis import Redis

from app.config import SeparatorProfile, Settings, settings
from app.core.audio import get_audio_duration, resolve_trim_window

logger = logging.getLogger(__name__)

_SEPARATOR_SLOT_PREFIX = "voiceprint:separator-slot:"
_SEPARATOR_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""
_separator_redis_client: Redis | None = None


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=5)
    except Exception:
        logger.debug("Failed to terminate subprocess cleanly pid=%s", process.pid, exc_info=True)

    if process.poll() is not None:
        return

    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait(timeout=5)
    except Exception:
        logger.debug("Failed to kill subprocess pid=%s", process.pid, exc_info=True)


def _run_subprocess(
    cmd: list[str],
    *,
    timeout: int,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        start_new_session=(os.name == "posix"),
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(exc.cmd, exc.timeout, output=stdout, stderr=stderr) from exc
    except BaseException:
        _terminate_process_tree(process)
        process.communicate()
        raise

    return subprocess.CompletedProcess(
        args=cmd,
        returncode=process.returncode,
        stdout=stdout,
        stderr=stderr,
    )


def _with_repo_pythonpath(env: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(env or os.environ)
    repo_root = "/app"
    existing = merged.get("PYTHONPATH", "")
    paths = [repo_root]
    if existing:
        paths.append(existing)
    merged["PYTHONPATH"] = os.pathsep.join(paths)
    return merged


def _get_separator_redis_client(redis_url: str) -> Redis:
    global _separator_redis_client
    if _separator_redis_client is None:
        _separator_redis_client = Redis.from_url(redis_url, decode_responses=True)
    return _separator_redis_client


class VocalSeparator:
    """Strip accompaniment, returning a vocals-only WAV for the active profile."""

    def __init__(
        self,
        cfg: Settings | None = None,
        profile: SeparatorProfile | None = None,
    ):
        self.cfg = cfg or settings
        self.profile = profile or self.cfg.get_separator_profile()
        self.model_dir = self.cfg.separator_model_dir
        self.cache_dir = self.cfg.separator_cache_dir
        os.makedirs(self.model_dir, exist_ok=True)
        if self.cfg.separator_cache_enabled:
            os.makedirs(self.cache_dir, exist_ok=True)

    def separate(
        self,
        wav_path: str,
        *,
        max_duration_seconds: int | float | None | object = ...,
    ) -> tuple[str, str]:
        """Run vocal separation on *wav_path*.

        Returns ``(vocals_wav_path, work_dir)``.  The caller **must** call
        ``shutil.rmtree(work_dir, ignore_errors=True)`` when done.

        On any failure the original *wav_path* is returned unchanged so the
        pipeline degrades gracefully without crashing.
        """
        work_dir = tempfile.mkdtemp(prefix=f"{self.profile.id}_")
        try:
            trim_limit = self.cfg.separator_max_seconds if max_duration_seconds is ... else max_duration_seconds
            trimmed = self._trim_input(wav_path, work_dir, max_duration_seconds=trim_limit)
            cache_key = self._build_cache_key(trimmed, max_duration_seconds=trim_limit)
            cached = self._restore_cached_output(cache_key, work_dir)
            if cached is not None:
                logger.info("Vocal separation cache hit profile=%s", self.profile.id)
                return cached, work_dir

            with self._limit_concurrency():
                vocals_path = self._run_backend(trimmed, work_dir)
            if vocals_path is None or not os.path.exists(vocals_path):
                logger.warning(
                    "Separator profile %s produced no vocals output — falling back.",
                    self.profile.id,
                )
                return wav_path, work_dir

            self._save_cached_output(cache_key, vocals_path)
            logger.info(
                "Vocal separation OK profile=%s backend=%s model=%s → %s",
                self.profile.id,
                self.profile.backend,
                self.profile.model,
                vocals_path,
            )
            return vocals_path, work_dir

        except Exception:
            logger.exception(
                "Vocal separation error profile=%s backend=%s — falling back.",
                self.profile.id,
                self.profile.backend,
            )
            return wav_path, work_dir

    @contextmanager
    def _limit_concurrency(self):
        max_slots = max(1, int(self.cfg.separator_max_concurrent_jobs))
        lease_key: str | None = None
        token = uuid.uuid4().hex
        wait_logged = False
        client: Redis | None = None

        try:
            client = _get_separator_redis_client(self.cfg.redis_url)
        except Exception:
            logger.warning(
                "Separator concurrency control unavailable; continuing without global throttling.",
                exc_info=True,
            )
            yield
            return

        lease_ttl_seconds = max(self.cfg.separator_timeout_seconds + 120, 300)
        wait_started = time.monotonic()

        while lease_key is None:
            for slot in range(max_slots):
                candidate_key = f"{_SEPARATOR_SLOT_PREFIX}{slot}"
                try:
                    acquired = client.set(candidate_key, token, nx=True, ex=lease_ttl_seconds)
                except Exception:
                    logger.warning(
                        "Separator concurrency control failed mid-wait; continuing without global throttling.",
                        exc_info=True,
                    )
                    yield
                    return
                if acquired:
                    lease_key = candidate_key
                    break

            if lease_key is not None:
                waited = time.monotonic() - wait_started
                if waited >= 1.0:
                    logger.info(
                        "Acquired separator slot after waiting %.1fs (max_concurrent=%d)",
                        waited,
                        max_slots,
                    )
                break

            if not wait_logged:
                logger.info(
                    "Waiting for separator capacity (max_concurrent=%d)",
                    max_slots,
                )
                wait_logged = True
            time.sleep(1.0)

        try:
            yield
        finally:
            if lease_key is None or client is None:
                return
            try:
                client.eval(_SEPARATOR_RELEASE_SCRIPT, 1, lease_key, token)
            except Exception:
                logger.debug("Failed to release separator slot %s", lease_key, exc_info=True)

    def _trim_input(
        self,
        wav_path: str,
        work_dir: str,
        *,
        max_duration_seconds: int | float | None,
    ) -> str:
        try:
            duration = get_audio_duration(wav_path)
        except Exception:
            duration = None

        start, limit = resolve_trim_window(duration, max_duration_seconds)

        # Keep the full-fidelity source whenever it already fits in the
        # separator window. Separation quality drops noticeably if we pre-downsample.
        if start <= 0 and limit is None:
            return wav_path

        trimmed = os.path.join(work_dir, "input.wav")
        cmd = ["ffmpeg"]
        if start > 0:
            cmd += ["-ss", f"{start:.3f}"]
        cmd += [
            "-i", wav_path,
        ]
        if limit is not None:
            cmd += ["-t", f"{limit:.3f}"]
        cmd += [
            "-vn",
            "-c:a", "pcm_s16le",
            "-y", trimmed,
        ]
        result = _run_subprocess(
            cmd,
            timeout=min(180, self.cfg.separator_timeout_seconds),
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                output=result.stdout,
                stderr=result.stderr,
            )
        return trimmed

    def _run_backend(self, trimmed_path: str, work_dir: str) -> str | None:
        if self.profile.backend == "demucs":
            return self._run_demucs(trimmed_path, work_dir)
        if self.profile.backend == "audio-separator":
            return self._run_audio_separator(trimmed_path, work_dir)
        raise ValueError(f"Unsupported separator backend: {self.profile.backend}")

    def _run_demucs(self, trimmed_path: str, work_dir: str) -> str | None:
        cmd = [
            "python",
            "-m",
            "demucs",
            "--two-stems",
            "vocals",
            "-n",
            self.profile.model,
            "--clip-mode",
            "rescale",
            "-o",
            work_dir,
            trimmed_path,
        ]
        try:
            result = _run_subprocess(
                cmd,
                timeout=self.cfg.separator_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Demucs timed out after %ss for profile=%s — falling back.",
                self.cfg.separator_timeout_seconds,
                self.profile.id,
            )
            return None
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")[-600:]
            logger.warning(
                "Demucs exited %d for profile=%s — falling back.\n%s",
                result.returncode,
                self.profile.id,
                stderr,
            )
            return None

        candidates = sorted(
            (
                path
                for path in Path(work_dir).rglob("vocals.wav")
                if path.is_file()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return None
        return str(candidates[0])

    def _run_audio_separator(self, trimmed_path: str, work_dir: str) -> str | None:
        cmd = [
            "audio-separator",
            trimmed_path,
            "--output_dir",
            work_dir,
            "--model_file_dir",
            self.model_dir,
            "--single_stem",
            "Vocals",
            "--sample_rate",
            "16000",
            "--output_format",
            "WAV",
            "-m",
            self.profile.model,
        ]
        try:
            result = _run_subprocess(
                cmd,
                env=_with_repo_pythonpath(),
                timeout=self.cfg.separator_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "audio-separator timed out after %ss for profile=%s — falling back.",
                self.cfg.separator_timeout_seconds,
                self.profile.id,
            )
            return None
        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")[-600:]
            logger.warning(
                "audio-separator exited %d for profile=%s — falling back.\n%s",
                result.returncode,
                self.profile.id,
                stderr,
            )
            return None

        candidates = sorted(
            (
                path
                for path in Path(work_dir).rglob("*")
                if path.is_file() and "vocals" in path.name.lower() and path.suffix.lower() in {".wav", ".flac", ".mp3"}
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            return None
        return str(candidates[0])

    def _build_cache_key(self, trimmed_path: str, *, max_duration_seconds: int | float | None) -> str:
        digest = hashlib.sha1()
        digest.update(self.profile.backend.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.profile.model.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(max_duration_seconds).encode("utf-8"))
        with open(trimmed_path, "rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _cache_path(self, cache_key: str) -> str:
        return os.path.join(self.cache_dir, self.profile.id, f"{cache_key}.wav")

    def _restore_cached_output(self, cache_key: str, work_dir: str) -> str | None:
        if not self.cfg.separator_cache_enabled:
            return None
        cached_path = self._cache_path(cache_key)
        if not os.path.exists(cached_path):
            return None
        restored_path = os.path.join(work_dir, "vocals.cached.wav")
        shutil.copyfile(cached_path, restored_path)
        return restored_path

    def _save_cached_output(self, cache_key: str, vocals_path: str) -> None:
        if not self.cfg.separator_cache_enabled:
            return
        cached_path = self._cache_path(cache_key)
        os.makedirs(os.path.dirname(cached_path), exist_ok=True)
        shutil.copyfile(vocals_path, cached_path)
