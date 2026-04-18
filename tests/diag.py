#!/usr/bin/env python3
"""Minimal script to diagnose 422 error from enroll endpoint."""
import io, math, struct, wave, json
import urllib.request, urllib.error

def make_voice_wav(freq=150.0, dur=5.5, sr=16000):
    n = int(sr * dur)
    frames = []
    for i in range(n):
        t = i / sr
        am = 0.55 + 0.45 * math.sin(2 * math.pi * 4.0 * t)
        f0 = freq + 5 * math.sin(2 * math.pi * 0.3 * t)
        signal = sum((1.0 / k) * math.sin(2 * math.pi * k * f0 * t) for k in range(1, 7))
        frames.append(max(-32767, min(32767, int(32767 * signal * am * 0.35))))
    buf = io.BytesIO()
    with wave.open(buf, 'w') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(struct.pack(f'<{n}h', *frames))
    return buf.getvalue()

wav = make_voice_wav()
boundary = 'b12345'
parts = []
parts.append('--' + boundary + '\r\n')
parts.append('Content-Disposition: form-data; name="speaker_name"\r\n\r\n')
parts.append('smoke_diag\r\n')
parts.append('--' + boundary + '\r\n')
parts.append('Content-Disposition: form-data; name="audio"; filename="a.wav"\r\n')
parts.append('Content-Type: audio/wav\r\n\r\n')
body = ''.join(parts).encode() + wav + ('\r\n--' + boundary + '--\r\n').encode()

req = urllib.request.Request(
    'http://localhost:8000/api/v1/enroll',
    data=body,
    headers={'Content-Type': 'multipart/form-data; boundary=' + boundary},
    method='POST'
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        print('Status:', r.status)
        print('Body:', r.read().decode())
except urllib.error.HTTPError as e:
    print('Status:', e.code)
    print('Body:', e.read().decode())
