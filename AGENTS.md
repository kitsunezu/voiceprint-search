# AGENTS.md

## Deployment

- Pushes to `main` run `.github/workflows/publish-images.yml`, build and push `ghcr.io/kitsunezu/voiceprint-search-frontend:main` and `ghcr.io/kitsunezu/voiceprint-search-ai-service:main`, only after the separate CI workflow succeeds, then join Tailscale with this repository's GitHub OIDC identity and trigger Coolify.
- The Coolify resource is the `voiceprint-search` Compose service.
- GitHub Actions requires `TS_OAUTH_CLIENT_ID`, `TS_AUDIENCE`, and `COOLIFY_DEPLOY_TOKEN` secrets. Keep their values out of git.

## Deployment verification

- Production builds receive `BUILD_REVISION` from the exact GitHub commit. The workflow polls public release/health endpoints until their revision matches that commit; an old healthy image cannot satisfy deployment success.
- The live Coolify Compose resource is managed separately from the repository example. App images must use `pull_policy: always`; preserve the existing persistent volumes and runtime environment when editing it.
- Repository Compose files are examples; runtime changes must be applied deliberately in the existing Coolify resource. CI publishes images and redeploys that saved definition; it does not import example Compose or recreate database volumes.
