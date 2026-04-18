"""Test separator + VAD pipeline using actual modules."""
import sys
sys.path.insert(0, '/app')

from app.core.separator import VocalSeparator
from app.core.audio import normalize_audio
from app.core.vad import VoiceActivityDetector
import scipy.io.wavfile as wav
import os

sep = VocalSeparator()
vad = VoiceActivityDetector()

test = sys.argv[1] if len(sys.argv) > 1 else '/tmp/speaker_a.wav'
print(f"Test file: {test}")

norm = normalize_audio(test)
sr0, d0 = wav.read(norm)
print(f"[1] normalized: sr={sr0}, duration={len(d0)/sr0:.1f}s")

vocals, work_dir = sep.separate(norm)
print(f"[2] separator returned: {vocals}")
print(f"[2] fallback (==norm)? {vocals == norm}")

if vocals != norm:
    sr1, d1 = wav.read(vocals)
    print(f"[2] vocals.wav sr={sr1}, duration={len(d1)/sr1:.1f}s")

    norm2 = normalize_audio(vocals)
    sr2, d2 = wav.read(norm2)
    print(f"[3] normalize_audio(vocals): sr={sr2}, duration={len(d2)/sr2:.1f}s")

    ts, _ = vad.detect_speech(norm2)
    print(f"[4] VAD timestamps: {len(ts)}")
    if ts:
        total = sum(t["end"] - t["start"] for t in ts) / 16000
        print(f"[4] total speech: {total:.2f}s")
        speech = vad.extract_speech(norm2, min_speech_seconds=3.0)
        print(f"[4] extract_speech: {'None' if speech is None else str(round(len(speech)/16000,2))+'s'}")
    else:
        print("[4] VAD: no speech detected after separation!")
else:
    print("[2] Demucs failed — testing VAD on original")
    ts, _ = vad.detect_speech(norm)
    print(f"[3] VAD on original: {len(ts)} timestamps")
