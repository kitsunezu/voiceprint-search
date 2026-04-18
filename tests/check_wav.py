#!/usr/bin/env python3
"""Check espeak WAV files and run VAD test."""
import scipy.io.wavfile as wav_io
import numpy as np

for name in ['speaker_a', 'speaker_b']:
    sr, data = wav_io.read(f'/tmp/{name}.wav')
    dur = len(data) / sr
    print(f'{name}: sr={sr} shape={data.shape} dtype={data.dtype} duration={dur:.1f}s')
