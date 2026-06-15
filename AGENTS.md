# AGENTS.md

## Deployment

- Pushes to `main` run `.github/workflows/publish-images.yml`, build and push `ghcr.io/kitsunezu/voiceprint-search-frontend:main` and `ghcr.io/kitsunezu/voiceprint-search-ai-service:main`, then call Portainer's Git stack redeploy API.
- The Portainer stack is `voiceprint-search`, stack id `39`, on endpoint id `3`.
- Keep the Portainer API key in the `PORTAINER_API_KEY` GitHub Actions secret only; do not commit it.
- Portainer sits behind Cloudflare Access. The deploy workflow must pass the service token stored in `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` GitHub Actions secrets.
- Do not commit Portainer API keys, Cloudflare Access service token values, cookies, passwords, or webhook URLs. Only secret and variable names belong in git.
