# Fixel API + UI for a public deployment: `docker build -t fixel . && docker run -p 8765:8765 -v fixel-data:/app/.fixel --env-file .env fixel`
# The API key comes from the environment at run time (MODEL_API_KEY); it is never baked into the image.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    FIXEL_PUBLIC=1 FIXEL_MODE=record FIXEL_CONFIG_ROOTS=/app/targets/demo-shop.yaml
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# The repo itself, .git included: fixes run in a git worktree of the vendored demo-shop.
COPY . .
RUN pip install -e . \
 && playwright install --with-deps chromium \
 && npm ci \
 && (cd targets/demo-shop && npm ci) \
 && (cd web && npm ci && npm run build) \
 && git config --system user.email fixel@localhost && git config --system user.name fixel \
 && useradd -m fixel && mkdir -p .fixel && chown -R fixel /app /ms-playwright

USER fixel
EXPOSE 8765
VOLUME /app/.fixel
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fsS http://127.0.0.1:8765/api/config >/dev/null || exit 1
# FIXEL_TRUST_PROXY=1 only when a proxy you control (Caddy, Fly, Vercel's rewrite) sets X-Forwarded-For.
CMD ["fixel", "serve", "--public", "--host", "0.0.0.0", "--port", "8765"]
