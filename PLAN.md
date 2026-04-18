# Voiceprint Search — Voice Identification Platform

## Overview

Voiceprint Search is a self-hosted voice identification platform that uses AI speaker embeddings
to verify whether two audio clips belong to the same person (1:1 verification) and to
search for the most similar voice in a database of enrolled speakers (1:N identification).

**Key capabilities:**

- **1:1 Verification** — Upload two audio clips, get a calibrated probability that they are the same speaker
- **1:N Search** — Upload one audio clip, find the most similar speakers in the database with ranked scores
- **Speaker Enrollment** — Register a speaker with one or more audio samples
- **Optional Vocal Separation** — Extract vocals from music before analysis (async)

**Constraints:**

| Item               | Value                                         |
| ------------------ | --------------------------------------------- |
| Target scale       | ≤ 2,000 enrolled speakers                     |
| Deployment target  | unRAID OS, Docker (Portainer)                  |
| Hardware           | AMD Ryzen AI 9 HX PRO 370, 32 GB RAM          |
| GPU                | Radeon 890M iGPU (optional; CPU-first design)  |
| Observability      | SigNoz (existing)                              |
| Access model       | Public website                                 |

---

## Architecture

```
┌──────────────┐       ┌──────────────────┐       ┌────────────────┐
│   Browser    │──────▶│  Frontend / BFF  │──────▶│  AI Service    │
│              │◀──────│  (Next.js)       │◀──────│  (FastAPI)     │
└──────────────┘       └────────┬─────────┘       └───────┬────────┘
                                │                         │
                       ┌────────▼─────────┐       ┌───────▼────────┐
                       │  Nginx Proxy Mgr │       │  Worker        │
                       │  (existing)      │       │  (Dramatiq)    │
                       └──────────────────┘       └───────┬────────┘
                                                          │
              ┌───────────────┬───────────────┬───────────┘
              ▼               ▼               ▼
     ┌────────────┐  ┌───────────────┐  ┌──────────┐
     │ PostgreSQL │  │    MinIO       │  │  Redis   │
     │ + pgvector │  │ (file storage) │  │ (queue)  │
     └────────────┘  └───────────────┘  └──────────┘
```

All services run as Docker containers on unRAID, orchestrated via Docker Compose / Portainer.

---

## Services & Technology Stack

### 1. Frontend / BFF — `frontend`

| Role        | Technologies                                    |
| ----------- | ----------------------------------------------- |
| Framework   | Next.js 15, React 19, TypeScript                |
| Styling     | Tailwind CSS v4                                 |
| HTTP client | Native `fetch` (server-side proxy to AI service)|
| Validation  | Zod                                             |
| Telemetry   | OpenTelemetry JS SDK → SigNoz                   |

**Responsibilities:**

- Serve upload UI (verify, search, enroll pages)
- Validate file size / type / rate limits before proxying to AI service
- Forward requests to AI service via internal Docker network
- Display results with calibrated probability scores
- Never expose AI service directly to the internet

### 2. AI Inference Service — `ai-service`

| Role                | Technologies                                  |
| ------------------- | --------------------------------------------- |
| Framework           | FastAPI, Uvicorn, Pydantic v2                 |
| Audio normalisation | FFmpeg (subprocess)                           |
| Voice activity      | Silero VAD (via `torch.hub`)                  |
| Speaker embeddings  | SpeechBrain ECAPA-TDNN (192-dim vectors)      |
| Score calibration   | Logistic calibration (scipy)                  |
| Vocal separation    | Demucs v4 (optional, async via worker)        |
| ORM / DB            | SQLAlchemy 2.0 (async) + asyncpg + pgvector   |
| Object storage      | MinIO Python SDK                              |
| Telemetry           | OpenTelemetry Python SDK → SigNoz             |

**Responsibilities:**

- Receive audio, normalise to mono 16 kHz WAV
- Detect speech segments via VAD; reject no-speech clips
- Compute 192-dim speaker embedding via ECAPA-TDNN
- 1:1 verify: cosine similarity → calibrated probability
- 1:N search: pgvector nearest-neighbor query → ranked results
- Enroll: persist embedding + metadata in PostgreSQL
- Dispatch slow jobs (vocal separation, long audio) to worker queue

### 3. Background Worker — `worker`

| Role    | Technologies                                       |
| ------- | -------------------------------------------------- |
| Queue   | Dramatiq + Redis broker                            |
| Tasks   | Vocal separation (Demucs), batch re-embed, re-index|

Same Python codebase as ai-service, different entrypoint (`dramatiq app.worker.tasks`).

### 4. PostgreSQL + pgvector — `db`

| Role         | Technologies                   |
| ------------ | ------------------------------ |
| Database     | PostgreSQL 16                  |
| Vector index | pgvector extension (IVFFlat)   |
| Migrations   | Alembic (future)               |

**Stores:** speakers, audio_assets, embeddings (192-dim vectors), verification/search job logs.

### 5. Redis — `redis`

| Role    | Technologies |
| ------- | ------------ |
| Broker  | Redis 7      |

Used for Dramatiq job queue, rate limiting, and transient caching.

### 6. MinIO — `minio`

| Role           | Technologies       |
| -------------- | -------------------|
| Object storage | MinIO (S3-compat)  |

Stores original audio uploads, processed WAV files, separated vocal tracks.

### 7. SigNoz — *(existing)*

All services emit traces and metrics via OpenTelemetry Collector to SigNoz.

---

## Data Flow

### Enroll Speaker

```
Browser → POST /api/enroll (file + name)
  → Frontend validates → proxy to AI Service
    → FFmpeg normalise → Silero VAD → ECAPA-TDNN embed
    → Store audio in MinIO
    → Store speaker + embedding in PostgreSQL
  ← { speaker_id, message }
```

### 1:1 Verify

```
Browser → POST /api/verify (file_a + file_b)  OR  (file + speaker_id)
  → Frontend validates → proxy to AI Service
    → Normalise both → VAD → Embed both
    → Cosine similarity → Logistic calibration → probability
  ← { score, probability, is_same_speaker }
```

### 1:N Search

```
Browser → POST /api/search (file, limit=10)
  → Frontend validates → proxy to AI Service
    → Normalise → VAD → Embed
    → pgvector: SELECT ... ORDER BY vector <=> query LIMIT N
    → Calibrate each score
  ← { results: [{ speaker_id, name, score, probability }] }
```

---

## API Contract (AI Service)

### `POST /api/v1/enroll`

| Param        | Type   | Required | Description                   |
| ------------ | ------ | -------- | ----------------------------- |
| audio        | file   | yes      | Audio file (mp3/wav/flac/ogg) |
| speaker_name | string | yes      | Display name for the speaker  |

Response `201`:
```json
{ "speaker_id": 1, "embedding_id": 1, "message": "Speaker enrolled" }
```

### `POST /api/v1/verify`

| Param      | Type   | Required | Description                             |
| ---------- | ------ | -------- | --------------------------------------- |
| audio_a    | file   | yes      | First audio clip                        |
| audio_b    | file   | cond.    | Second audio clip (if no speaker_id)    |
| speaker_id | int    | cond.    | Compare against enrolled speaker        |

Response `200`:
```json
{
  "score": 0.82,
  "probability": 0.91,
  "is_same_speaker": true,
  "threshold": 0.65
}
```

### `POST /api/v1/search`

| Param | Type | Required | Description               |
| ----- | ---- | -------- | ------------------------- |
| audio | file | yes      | Query audio clip          |
| limit | int  | no       | Max results (default: 10) |

Response `200`:
```json
{
  "results": [
    { "speaker_id": 3, "speaker_name": "Alice", "score": 0.87, "probability": 0.94, "rank": 1 },
    { "speaker_id": 7, "speaker_name": "Bob",   "score": 0.62, "probability": 0.58, "rank": 2 }
  ]
}
```

### `GET /api/v1/speakers`

Response `200`:
```json
{
  "speakers": [
    { "id": 1, "name": "Alice", "embedding_count": 3, "created_at": "..." }
  ]
}
```

### `GET /api/v1/health`

Response `200`:
```json
{ "status": "ok", "model_loaded": true, "db_connected": true }
```

---

## Database Schema

```sql
-- Enabled by: CREATE EXTENSION IF NOT EXISTS vector;

speakers
  id            SERIAL PRIMARY KEY
  name          VARCHAR(255) NOT NULL
  description   TEXT
  created_at    TIMESTAMPTZ DEFAULT NOW()
  updated_at    TIMESTAMPTZ DEFAULT NOW()

audio_assets
  id                SERIAL PRIMARY KEY
  speaker_id        INTEGER → speakers(id)
  original_filename VARCHAR(512)
  storage_key       VARCHAR(512)        -- MinIO object key
  duration_seconds  REAL
  sample_rate       INTEGER
  has_speech        BOOLEAN DEFAULT TRUE
  created_at        TIMESTAMPTZ DEFAULT NOW()

embeddings
  id              SERIAL PRIMARY KEY
  speaker_id      INTEGER → speakers(id) ON DELETE CASCADE
  audio_asset_id  INTEGER → audio_assets(id) ON DELETE CASCADE
  vector          vector(192)           -- ECAPA-TDNN output dim
  model_version   VARCHAR(100) DEFAULT 'ecapa-tdnn-v1'
  created_at      TIMESTAMPTZ DEFAULT NOW()

-- IVFFlat index for cosine similarity search
CREATE INDEX ON embeddings USING ivfflat (vector vector_cosine_ops) WITH (lists = 50);
```

---

## Score Calibration

The ECAPA-TDNN model outputs cosine similarity scores in [-1, 1].
These are **not** probabilities. To display a meaningful "probability of same speaker":

1. Collect a validation set of same-speaker and different-speaker pairs
2. Fit a logistic regression: `P(same) = sigmoid(w * score + b)`
3. Default parameters (pre-tuned on VoxCeleb): `w ≈ 10.0, b ≈ -3.5`
4. Re-calibrate when switching models or adding domain-specific data

---

## Deployment

### Docker Compose services

| Service    | Image                              | Port (host) | Notes                         |
| ---------- | ---------------------------------- | ----------- | ----------------------------- |
| frontend   | voiceprint-frontend:latest         | 3010        | Exposed via Nginx Proxy Mgr   |
| ai-service | voiceprint-ai:latest               | (internal)  | Not exposed to internet       |
| worker     | voiceprint-ai:latest               | —           | Same image, different CMD     |
| db         | pgvector/pgvector:pg16             | (internal)  | Persistent volume             |
| redis      | redis:7-alpine                     | (internal)  |                               |
| minio      | minio/minio:latest                 | 9000/9001   | Console on 9001 (optional)    |

### Volumes

- `pgdata` — PostgreSQL data
- `minio-data` — MinIO buckets
- `redis-data` — Redis AOF (optional)
- `model-cache` — Pre-downloaded AI models (shared between ai-service and worker)

### Networking

All services on a single Docker bridge network `voiceprint-net`.
Only `frontend` and optionally `minio` console are reachable from Nginx Proxy Manager.

### Nginx Proxy Manager routes

| Domain / Path                | Target              |
| ---------------------------- | ------------------- |
| `voice.kitsunet.app`         | frontend:3000       |
| `voice.kitsunet.app/minio`   | minio:9001 (opt.)   |

---

## Development Setup

### Prerequisites

- Docker & Docker Compose
- Node.js 20+ (for frontend local dev)
- Python 3.11+ (for AI service local dev)
- FFmpeg installed locally

### Quick start

```bash
# Start infrastructure
docker compose up -d db redis minio

# AI service (local)
cd ai-service
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (local)
cd frontend
npm install
npm run dev
```

### Full stack (Docker)

```bash
docker compose up --build
```

---

## Security & Privacy

- **Biometric data**: Voice embeddings are biometric identifiers. Display consent notice before upload.
- **Rate limiting**: Redis-backed rate limiter on upload endpoints (e.g., 10 req/min per IP).
- **File validation**: Accept only audio MIME types, max 50 MB, reject executables.
- **Retention**: Auto-delete unlinked audio assets after configurable retention window.
- **Network isolation**: AI service, DB, Redis, MinIO are internal-only; never exposed to internet.
- **No auth in MVP**: Acceptable for a personal/demo tool; add authentication before wider use.

---

## Roadmap

1. **MVP** — 1:1 verify + 1:N search + enroll + basic UI ← *current target*
2. **Vocal separation** — Async Demucs pipeline for music → vocal extraction
3. **Audio tools frontend** — Separate UI for general audio processing (separation, trimming, format conversion)
4. **Authentication** — User accounts, API keys, usage quotas
5. **GPU acceleration** — ONNX Runtime + DirectML for AMD iGPU (validate on target hardware first)
6. **Anti-spoofing** — Liveness / replay detection
7. **Batch import** — Bulk enroll speakers from audio archives
