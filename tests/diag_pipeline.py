"""Diagnose preprocessing pipeline step by step."""
import subprocess, os, sys, tempfile
import scipy.io.wavfile as wav
import numpy as np

sys.path.insert(0, '/app')
from app.core.audio import normalize_audio
from app.core.vad import VoiceActivityDetector

test_file = sys.argv[1] if len(sys.argv) > 1 else '/tmp/speaker_a.wav'
print(f"=== Diagnosing: {test_file} ===\n")

# Step 0: original
sr, data = wav.read(test_file)
print(f"[0] 原始音訊: sr={sr}, channels={'stereo' if data.ndim>1 else 'mono'}, duration={len(data)/sr:.1f}s")

# Step 1: normalize
norm_path = normalize_audio(test_file)
sr1, d1 = wav.read(norm_path)
print(f"[1] normalize_audio: sr={sr1}, duration={len(d1)/sr1:.1f}s")

# Step 2: Demucs
work_dir = tempfile.mkdtemp(prefix="diag_demucs_")
trimmed = os.path.join(work_dir, "input.wav")
subprocess.run(["ffmpeg","-i",norm_path,"-t","90","-ac","1","-ar","16000","-y",trimmed],
               capture_output=True, check=True)
sr2, d2 = wav.read(trimmed)
print(f"[2] Demucs 輸入: sr={sr2}, duration={len(d2)/sr2:.1f}s")

result = subprocess.run(
    ["python","-m","demucs","--two-stems","vocals","-n","htdemucs","--clip_mode","rescale","-o",work_dir,trimmed],
    capture_output=True, timeout=300
)
print(f"[3] Demucs returncode={result.returncode}")
if result.returncode != 0:
    print("  stderr:", result.stderr.decode(errors="replace")[-400:])
    sys.exit(1)

vocals_path = os.path.join(work_dir, "htdemucs", "input", "vocals.wav")
if not os.path.exists(vocals_path):
    print("[3] ERROR: vocals.wav 不存在，Demucs 失敗")
    sys.exit(1)

sr3, d3 = wav.read(vocals_path)
print(f"[3] vocals.wav: sr={sr3}, shape={d3.shape}, duration={len(d3)/sr3:.1f}s")

# Step 3: re-normalize vocals
norm_vocals = normalize_audio(vocals_path)
sr4, d4 = wav.read(norm_vocals)
print(f"[4] normalize_audio(vocals): sr={sr4}, duration={len(d4)/sr4:.1f}s")

# Step 4: VAD
vad = VoiceActivityDetector()
ts, wav_tensor = vad.detect_speech(norm_vocals)
print(f"[5] VAD timestamp count: {len(ts)}")
if ts:
    total = sum(t["end"] - t["start"] for t in ts) / 16000
    print(f"[5] VAD total speech detected: {total:.2f}s")
    speech = vad.extract_speech(norm_vocals, min_speech_seconds=3.0)
    print(f"[5] extract_speech result: {'None (too short)' if speech is None else f'{len(speech)/16000:.2f}s'}")
else:
    # Try without re-normalizing vocals
    print("[5] VAD failed on normalized vocals. Trying directly on raw vocals.wav...")
    ts_raw, _ = vad.detect_speech(vocals_path)
    print(f"[5] VAD on raw vocals (sr={sr3}): {len(ts_raw)} timestamps")
    if ts_raw:
        total2 = sum(t["end"] - t["start"] for t in ts_raw) / sr3
        print(f"[5] speech in raw sample domain: {total2:.2f}s (but sr mismatch!)")

print("\nDone.")
