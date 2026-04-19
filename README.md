# Voiceprint Search

Voiceprint Search is a self-hosted speaker identification platform for enrolling voices, verifying whether two clips belong to the same speaker, and searching a database for the closest speaker match.

It is designed as a Docker-first stack for small to medium voiceprint deployments, with a Next.js frontend, a FastAPI inference service, a background worker, PostgreSQL with pgvector, Redis, MinIO, and OpenTelemetry-based observability.

## Features

- Speaker enrollment with one or more audio samples
- One-to-one voice verification
- One-to-many voice search with ranked matches
- Multi-model embedding support
- Optional vocal separation and denoising pipeline
- Docker Compose local deployment
- GHCR image publishing through GitHub Actions
- Portainer stack deployment for server hosting

## Architecture

The system is split into six main services:

- frontend: Next.js application and backend-for-frontend layer
- ai-service: FastAPI service for preprocessing, embedding, verification, and search
- worker: Dramatiq worker for background jobs
- db: PostgreSQL 16 with pgvector
- redis: queue broker and transient storage
- minio: S3-compatible object storage for uploaded and processed audio

High-level request flow:

1. A user uploads audio through the frontend.
2. The frontend proxies requests to the internal AI service.
3. The AI service normalizes audio, runs speech detection, optionally separates vocals, and computes embeddings.
4. Metadata and vectors are stored in PostgreSQL, while files are stored in MinIO.
5. Search and verification results are returned to the frontend.

## Repository Layout

```text
.
├── ai-service/        FastAPI app, audio pipeline, worker tasks
├── frontend/          Next.js UI and API proxy routes
├── db/                SQL bootstrap and migrations
├── tests/             Diagnostic scripts and benchmark helpers
├── .github/workflows/ GitHub Actions CI/CD
├── docker-compose.yml Local deployment stack
└── portainer-stack.yml Production-style Portainer stack
```

## Core Capabilities

### Enrollment

Enroll a speaker with one or more voice samples. The platform extracts embeddings and stores both metadata and source audio for future verification and search.

### Verification

Compare two audio clips, or compare an uploaded clip with an enrolled speaker, and return a calibrated confidence score.

### Search

Upload one clip and retrieve the closest matching enrolled speakers using pgvector similarity search.

### Audio Preprocessing

The pipeline supports normalization, VAD-based speech trimming, denoising, and optional vocal separation for noisy or music-heavy inputs.

## Technology Stack

### Frontend

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS v4
- next-intl
- OpenTelemetry for tracing

### AI Service

- FastAPI
- Uvicorn
- Pydantic v2
- SpeechBrain ECAPA-TDNN
- Resemblyzer
- pyannote support hooks
- Demucs and audio-separator
- SQLAlchemy async
- pgvector
- MinIO SDK

### Infrastructure

- PostgreSQL 16
- Redis 7
- MinIO
- Docker Compose
- Portainer
- SigNoz / OTEL collector integration

## Quick Start

### Prerequisites

- Docker
- Docker Compose

### Run Locally

```bash
docker compose up -d --build
```

Default endpoints:

- Frontend: http://localhost:3010
- AI health check: http://localhost:8000/api/v1/health
- MinIO console: http://localhost:9001

### Stop the Stack

```bash
docker compose down
```

## Configuration

The main runtime configuration is provided through environment variables in Docker Compose or Portainer.

Common variables:

- DB_PASSWORD: PostgreSQL password
- MINIO_ACCESS_KEY: MinIO root username
- MINIO_SECRET_KEY: MinIO root password
- MINIO_BUCKET: object storage bucket name
- ENABLED_MODELS: comma-separated embedding model IDs, default ecapa-tdnn-v1
- NEXT_PUBLIC_SITE_URL: public frontend base URL used for canonical tags, sitemap, manifest, and social metadata
- OTEL_EXPORTER_OTLP_ENDPOINT: OTEL / SigNoz collector endpoint
- SEARCH_STRATEGY: best, centroid, or hybrid
- SEPARATOR_PROFILE: demucs, mdx, or roformer
- HF_TOKEN: optional Hugging Face token for gated models

By default the stack now runs only ECAPA-TDNN for enrollment, search, and verification. If you want to re-enable multi-model embeddings later, set ENABLED_MODELS to a comma-separated list such as ecapa-tdnn-v1,resemblyzer-v1.

## Deployment

### Local Docker Compose

Use [docker-compose.yml](docker-compose.yml) for local development and self-hosted testing.

### Portainer Stack

Use [portainer-stack.yml](portainer-stack.yml) when deploying from prebuilt container images in Portainer.

The stack is designed to:

- pull images from GHCR
- initialize the database schema on first deployment
- apply idempotent schema upgrades on redeploy for existing databases
- persist PostgreSQL, Redis, MinIO, and model cache volumes

If you deployed an older Portainer stack before the audio asset processing columns were added, redeploy the stack once so the db-init service can patch the existing PostgreSQL schema before frontend and ai-service start.

Before deploying, replace the default image references or set these variables in Portainer:

- FRONTEND_IMAGE
- AI_SERVICE_IMAGE
- NEXT_PUBLIC_SITE_URL
- DB_PASSWORD
- MINIO_ACCESS_KEY
- MINIO_SECRET_KEY
- OTEL_EXPORTER_OTLP_ENDPOINT

## CI/CD

GitHub Actions workflows are included for both validation and image publishing.

- [.github/workflows/ci.yml](.github/workflows/ci.yml): runs frontend build checks, Python syntax compilation, and Docker Compose config validation
- [.github/workflows/publish-images.yml](.github/workflows/publish-images.yml): builds and pushes frontend and AI service images to GHCR on main, tags, or manual dispatch

The worker uses the same image as ai-service with a different startup command.

## Notes on Build Size

The AI service image preloads several models during the Docker build so that first startup is faster. This improves runtime behavior, but it also means image builds are significantly heavier than a typical web application build.

Because of that, CI is split into:

- fast validation on every change
- image publishing only on main, tags, or manual release

## Intended Use

This project is currently optimized for self-hosted deployments and moderate speaker counts rather than internet-scale inference. It is a good fit for internal tools, private archives, controlled public interfaces, and research-oriented speaker search workflows.

## Related Files

- [docker-compose.yml](docker-compose.yml)
- [portainer-stack.yml](portainer-stack.yml)
- [PLAN.md](PLAN.md)
- [.github/workflows/ci.yml](.github/workflows/ci.yml)
- [.github/workflows/publish-images.yml](.github/workflows/publish-images.yml)