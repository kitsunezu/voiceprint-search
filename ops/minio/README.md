# MinIO security build

Build on the production host with `docker build -t kitsunet/minio:security-20261024 ops/minio`.
This uses the official final CE security release at a verified source commit and an updated Go compiler. The saved Coolify resource uses this local image with `pull_policy: never`; do not replace it with the older Docker Hub `latest` image.

This fixes CVE-2025-62506. It does not claim to fix subsequent 2026 advisories for which upstream directs CE users to AIStor. A switch to another distribution requires separate compatibility and licensing review.
