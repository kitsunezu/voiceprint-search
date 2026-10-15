# AGENTS.md

## Deployment

- Pushes to `main` run `.github/workflows/publish-images.yml`, build and push `ghcr.io/kitsunezu/voiceprint-search-frontend:main` and `ghcr.io/kitsunezu/voiceprint-search-ai-service:main`, only after the separate CI workflow succeeds, then join Tailscale with this repository's GitHub OIDC identity and trigger Coolify.
- The Coolify resource is the `voiceprint-search` Compose service.
- GitHub Actions requires `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE`, and `COOLIFY_DEPLOY_TOKEN` secrets. Keep their values out of git.
