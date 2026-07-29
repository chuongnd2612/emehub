# syntax=docker/dockerfile:1

# EmeHub backend (FastAPI, Python 3.13, uv).
#
# Since ADR 0007 the hub builds knowledge bases itself, so the image also carries
# what a build needs: git (shallow-clone the application repository), Node 20 and
# the Claude Code CLI (run `project-bootstrap` against the clone), and
# ca-certificates for outbound HTTPS.
#
# Chromium is deliberately NOT installed. QAgent ships it for DOM exploration and
# manual-login capture; ADR 0007 admits neither, and an unused browser in a
# credential-holding container is attack surface for nothing.
#
# Build context is the REPO ROOT (see docker-compose.yml) so the `skills/`
# directory the backend injects as a Claude system prompt can be copied in.
FROM python:3.13-slim-bookworm

# uv — fast, reproducible installs straight from api/uv.lock when it exists.
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /usr/local/bin/

# Node 20 runtime, copied from the official image (the Claude Code CLI is a Node
# package), plus git + ca-certificates. One layer so the apt lists and the npm
# cache never reach the published image.
COPY --from=node:20-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:20-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/api/.venv \
    PATH="/app/api/.venv/bin:${PATH}"

WORKDIR /app/api

# Dependencies first so the layer caches until the manifest changes.
COPY api/pyproject.toml ./
RUN uv sync --no-dev

# Backend source. api/.dockerignore keeps .venv / workspace / .env out.
COPY api/ ./

# The project-bootstrap skill, injected as the Claude system prompt for a build.
# Lands at /app/skills, which is `Settings.skills_path` (API_DIR.parent/skills).
COPY skills/ /app/skills/

# Bind on all interfaces so the web (nginx) container can reach the API.
# Secrets come from the environment (compose) — never baked into the image.
ENV EMEHUB_HOST=0.0.0.0 \
    EMEHUB_API_PORT=8790

EXPOSE 8790
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8790"]
