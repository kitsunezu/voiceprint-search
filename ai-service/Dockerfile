# ─────────────────────────────────────────────────────────────────────────────
# Stage 1 – builder: compile C-extension wheels and install all Python deps.
#   This stage carries build-essential (gcc, etc.) which adds ~200 MB; it is
#   discarded after the site-packages are copied to the runtime stage.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    libsndfile1-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

# ── 1. CPU-only PyTorch (saves ~2 GB over default CUDA build) ────────────────
# Install torch/torchaudio from the official CPU-only wheel index FIRST so
# that downstream packages (speechbrain, demucs) see them as already satisfied
# and never pull in the heavier CUDA variants.
RUN pip install --no-cache-dir \
    "torch>=2.0.0,<3.0.0" \
    "torchaudio>=2.0.0,<3.0.0" \
    --index-url https://download.pytorch.org/whl/cpu

# ── 2. Everything else (torch already satisfied → pip skips it) ──────────────
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 – runtime: slim image without build tools.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# Copy compiled packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages \
                    /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# Pre-download models during build so startup is fast.
# /models is mounted as a named volume at runtime; Docker initialises the
# volume with these files on first container start.
RUN python -c "\
from speechbrain.inference.speaker import EncoderClassifier; \
EncoderClassifier.from_hparams(source='speechbrain/spkrec-ecapa-voxceleb', savedir='/models/ecapa-tdnn')"

RUN python -c "\
import torch; \
torch.hub.load('snakers4/silero-vad', 'silero_vad', trust_repo=True)"

# Pre-download Resemblyzer encoder weights
RUN python -c "\
from resemblyzer import VoiceEncoder; \
VoiceEncoder(device='cpu')"

# Pre-download Demucs htdemucs model weights
RUN python -c "\
from demucs.pretrained import get_model; \
get_model('htdemucs')"

# audio-separator models are selected by runtime profile and download on first use.
# The model directory is mounted under /models so downloads persist across restarts.

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
