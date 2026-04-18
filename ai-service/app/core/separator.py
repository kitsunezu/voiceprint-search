"""Vocal/music source separation with switchable separator profiles.

The public interface remains a simple ``VocalSeparator.separate()`` call, but
the implementation can now switch between multiple backends such as Demucs and
audio-separator based MDX / Roformer models.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from app.config import SeparatorProfile, Settings, settings
from app.core.audio import get_audio_duration

logger = logging.getLogger(__name__)


def _with_repo_pythonpath(env: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(env or os.environ)
    repo_root = "/app"
    existing = merged.get("PYTHONPATH", "")
    paths = [repo_root]
    if existing:
        paths.append(existing)
    merged["PYTHONPATH"] = os.pathsep.join(paths)
    return merged


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

    def separate(self, wav_path: str) -> tuple[str, str]:
        """Run vocal separation on *wav_path*.

        Returns ``(vocals_wav_path, work_dir)``.  The caller **must** call
        ``shutil.rmtree(work_dir, ignore_errors=True)`` when done.

        On any failure the original *wav_path* is returned unchanged so the
        pipeline degrades gracefully without crashing.
        """
        work_dir = tempfile.mkdtemp(prefix=f"{self.profile.id}_")
        try:
            trimmed = self._trim_input(wav_path, work_dir)
            cache_key = self._build_cache_key(trimmed)
            cached = self._restore_cached_output(cache_key, work_dir)
            if cached is not None:
                logger.info("Vocal separation cache hit profile=%s", self.profile.id)
                return cached, work_dir

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

    def _trim_input(self, wav_path: str, work_dir: str) -> str:
        try:
            duration = get_audio_duration(wav_path)
        except Exception:
            duration = None

        # The upstream normalizer already produces mono 16 kHz WAV. If the
        # file is already within the separator window, avoid a second FFmpeg
        # decode/encode pass entirely.
        if duration is not None and duration <= (self.cfg.separator_max_seconds + 0.25):
            return wav_path

        trimmed = os.path.join(work_dir, "input.wav")
        subprocess.run(
            [
                "ffmpeg",
                "-i", wav_path,
                "-t", str(self.cfg.separator_max_seconds),
                "-ac", "1",
                "-ar", "16000",
                "-y", trimmed,
            ],
            capture_output=True,
            check=True,
            timeout=min(120, self.cfg.separator_timeout_seconds),
        )
        return trimmed

    def _run_backend(self, trimmed_path: str, work_dir: str) -> str | None:
        if self.profile.backend == "demucs":
            return self._run_demucs(trimmed_path, work_dir)
        if self.profile.backend == "audio-separator":
            return self._run_audio_separator(trimmed_path, work_dir)
        raise ValueError(f"Unsupported separator backend: {self.profile.backend}")

    def _run_demucs(self, trimmed_path: str, work_dir: str) -> str | None:
        result = subprocess.run(
            [
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
            ],
            capture_output=True,
            timeout=self.cfg.separator_timeout_seconds,
        )
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
        result = subprocess.run(
            [
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
            ],
            env=_with_repo_pythonpath(),
            capture_output=True,
            timeout=self.cfg.separator_timeout_seconds,
        )
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

    def _build_cache_key(self, trimmed_path: str) -> str:
        digest = hashlib.sha1()
        digest.update(self.profile.backend.encode("utf-8"))
        digest.update(b"\0")
        digest.update(self.profile.model.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(self.cfg.separator_max_seconds).encode("utf-8"))
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
