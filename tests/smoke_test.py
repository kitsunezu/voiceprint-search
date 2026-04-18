#!/usr/bin/env python3
"""
API smoke test — runs inside the voiceprint-ai container.
Tests: health, enroll (x2 speakers), search, verify.

Usage (from host):
  docker exec -i voiceprint-ai python /app/tests/smoke_test.py
"""
from __future__ import annotations

import io
import math
import struct
import sys
import wave
import json
import traceback
import urllib.error
import urllib.request

BASE = "http://localhost:8000/api/v1"
PASS = "\033[32m PASS\033[0m"
FAIL = "\033[31m FAIL\033[0m"


# ── Audio helpers ─────────────────────────────────────────────────────────────

def make_voice_wav(freq_hz: float = 150.0, duration: float = 5.0, sr: int = 16_000) -> bytes:
    """Generate a voice-like WAV:
    - Fundamental (F0) + 5 harmonics  → gives voiced speech harmonic structure
    - Slow AM at 4 Hz                 → simulates syllabic rhythm
    - Slight FM wobble                → simulates natural pitch variation

    Silero VAD is trained on speech features; the harmonic rich signal with
    AM modulation is much more likely to be flagged as speech than a pure sine.
    """
    n = int(sr * duration)
    frames: list[int] = []
    for i in range(n):
        t = i / sr
        # AM envelope: 4 Hz syllabic modulation
        am = 0.55 + 0.45 * math.sin(2 * math.pi * 4.0 * t)
        # FM wobble on fundamental (±5 Hz at 0.3 Hz)
        f0 = freq_hz + 5 * math.sin(2 * math.pi * 0.3 * t)
        # Voiced harmonics: decreasing amplitude
        signal = sum(
            (1.0 / k) * math.sin(2 * math.pi * k * f0 * t)
            for k in range(1, 7)
        )
        signal *= am * 0.35          # normalise
        frames.append(max(-32767, min(32767, int(32767 * signal))))

    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f"<{n}h", *frames))
    return buf.getvalue()


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def post_json(path: str, data: dict) -> tuple[int, dict]:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def post_multipart(path: str, fields: dict, file_bytes: bytes, filename: str = "audio.wav") -> tuple[int, dict]:
    boundary = "boundary12345"
    body_parts: list[bytes] = []
    for k, v in fields.items():
        body_parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
        )
    body_parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{filename}"\r\n'
        f'Content-Type: audio/wav\r\n\r\n'.encode()
        + file_bytes + b"\r\n"
    )
    body_parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(body_parts)

    req = urllib.request.Request(
        f"{BASE}{path}", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ── Test cases ────────────────────────────────────────────────────────────────

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = ""):
    results.append((name, ok, detail))
    icon = PASS if ok else FAIL
    print(f"{icon}  {name}", f"  ({detail})" if detail else "")


def test_health():
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=10) as r:
            data = json.loads(r.read())
        check("health", r.status == 200, str(data.get("status", data)))
    except Exception as e:
        check("health", False, str(e))


def test_models():
    try:
        with urllib.request.urlopen(f"{BASE}/models", timeout=10) as r:
            data = json.loads(r.read())
        check("GET /models", r.status == 200, f"{len(data)} model(s)")
    except Exception as e:
        check("GET /models", False, str(e))


enrolled_speaker_id: int | None = None


def test_enroll_speaker_a(audio_bytes: bytes):
    global enrolled_speaker_id
    status, data = post_multipart("/enroll", {"speaker_name": "smoke_a"}, audio_bytes)
    ok = status == 201 and "speaker_id" in data
    if ok:
        enrolled_speaker_id = data["speaker_id"]
    check("POST /enroll (speaker_a)", ok, f"status={status} id={data.get('speaker_id','?')}")


enrolled_speaker_b_id: int | None = None


def test_enroll_speaker_b(audio_bytes: bytes):
    global enrolled_speaker_b_id
    status, data = post_multipart("/enroll", {"speaker_name": "smoke_b"}, audio_bytes)
    ok = status == 201 and "speaker_id" in data
    if ok:
        enrolled_speaker_b_id = data["speaker_id"]
    check("POST /enroll (speaker_b)", ok, f"status={status} id={data.get('speaker_id','?')}")


def test_search(audio_bytes: bytes):
    status, data = post_multipart("/search", {"limit": "5"}, audio_bytes)
    ok = status == 200 and "results" in data
    check("POST /search", ok, f"status={status} hits={len(data.get('results', []))}")


def test_verify(audio_a: bytes, audio_b: bytes):
    boundary = "boundary_verify"
    body_parts: list[bytes] = []
    for name, wav in [("audio_a", audio_a), ("audio_b", audio_b)]:
        body_parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{name}.wav"\r\n'
            f'Content-Type: audio/wav\r\n\r\n'.encode()
            + wav + b"\r\n"
        )
    body_parts.append(f"--{boundary}--\r\n".encode())
    body = b"".join(body_parts)
    req = urllib.request.Request(
        f"{BASE}/verify", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            status = r.status
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        status = e.code
        data = json.loads(e.read())
    ok = status == 200 and "score" in data and "is_same_speaker" in data
    check("POST /verify", ok, f"status={status} score={data.get('score','?')} is_same_speaker={data.get('is_same_speaker','?')}")


def test_speakers():
    try:
        with urllib.request.urlopen(f"{BASE}/speakers", timeout=10) as r:
            data = json.loads(r.read())
        count = data.get("total", len(data.get("speakers", [])))
        check("GET /speakers", r.status == 200, f"total={count}")
    except Exception as e:
        check("GET /speakers", False, str(e))


def cleanup():
    """Delete smoke test speakers to leave DB clean."""
    for sid in [enrolled_speaker_id, enrolled_speaker_b_id]:
        if sid is None:
            continue
        req = urllib.request.Request(f"{BASE}/speakers/{sid}", method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n=== Voiceprint API Smoke Test ===\n")

    # Use real TTS speech files if available (generated by espeak-ng)
    # Fallback to synthetic audio (may fail VAD, validates error path)
    import os
    if os.path.exists('/tmp/speaker_a.wav') and os.path.exists('/tmp/speaker_b.wav'):
        with open('/tmp/speaker_a.wav', 'rb') as f:
            wav_a = f.read()
        with open('/tmp/speaker_b.wav', 'rb') as f:
            wav_b = f.read()
        print("  (using espeak-ng TTS audio)")
    else:
        wav_a = make_voice_wav(freq_hz=130, duration=5.5)  # lower pitched
        wav_b = make_voice_wav(freq_hz=260, duration=5.5)  # higher pitched
        print("  (using synthetic audio — VAD may reject)")

    test_health()
    test_models()
    test_enroll_speaker_a(wav_a)
    test_enroll_speaker_b(wav_b)
    test_search(wav_a)
    test_verify(wav_a, wav_b)
    test_speakers()
    cleanup()

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'='*34}")
    print(f"  Result: {passed}/{total} passed")
    print(f"{'='*34}\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
