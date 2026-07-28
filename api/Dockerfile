# syntax=docker/dockerfile:1

# EmeHub backend (FastAPI, Python 3.13, uv).
#
# Build context is the REPO ROOT (see docker-compose.yml) to match QAgent's
# shape and leave room for shared top-level directories later.
FROM python:3.13-slim-bookworm

# uv — fast, reproducible installs straight from api/uv.lock when it exists.
COPY --from=ghcr.io/astral-sh/uv:0.11.13 /uv /uvx /usr/local/bin/

ENV UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/api/.venv \
    PATH="/app/api/.venv/bin:${PATH}"

WORKDIR /app/api

# Dependencies first so the layer caches until the manifest changes.
COPY api/pyproject.toml ./
RUN uv sync --no-dev

# Backend source. api/.dockerignore keeps .venv / workspace / .env out.
COPY api/ ./

# Bind on all interfaces so the web (nginx) container can reach the API.
# Secrets come from the environment (compose) — never baked into the image.
ENV EMEHUB_HOST=0.0.0.0 \
    EMEHUB_API_PORT=8790

EXPOSE 8790
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8790"]
