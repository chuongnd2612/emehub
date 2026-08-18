# syntax=docker/dockerfile:1

# D-Agent (`ticket-executor`) — a hub-owned image for a sibling application.
#
# ## Why this file lives here and not in ticket-executor
#
# A hub task never modifies a sibling repository (CLAUDE.md › Sibling
# repositories), and D-Agent ships no container assets of its own. So the suite's
# deployment concern — "every app in the suite runs in a container on the shared
# network" — is satisfied from this side, with the sibling checkout used as the
# build context and nothing written into it.
#
# That makes the arrangement deliberately one-directional: this image tracks
# D-Agent's *current* layout (the source directories copied below, `npm run
# start`, Prisma migrations). If D-Agent restructures, this file breaks loudly at
# build time rather than shipping something subtly wrong. The long-term home for
# it is D-Agent itself — see docs/DAGENT-HANDOFF.md § 1.
#
# ## What the image carries
#
# Node 20 for Next 16, plus the two things a *run* needs: `git` and the Claude
# Code CLI, because D-Agent's whole purpose is to spawn `claude` inside a git
# repository. Chromium is not installed — D-Agent drives no browser.
#
# A containerised run still needs the repository it acts on and a logged-in
# Claude credential to be present *inside* the container; neither is something
# this image can bake in. See dagent/README.md § "What a containerised run can do".
FROM node:20-bookworm-slim

# git: a run branches, commits and pushes. ca-certificates: outbound HTTPS to the
# provider and to Anthropic. openssl: Prisma's query engine links against it.
# One layer, so neither the apt lists nor the npm cache reach the image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates openssl \
 && rm -rf /var/lib/apt/lists/* \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force

ENV NEXT_TELEMETRY_DISABLED=1 \
    NODE_ENV=production

WORKDIR /app

# Manifests first, so the dependency layer caches until they change.
#
# `npm ci` and not `npm ci --omit=dev`: `next start` is fine without dev
# dependencies, but `prisma migrate deploy` runs from the Prisma CLI at container
# start, and that CLI *is* a dev dependency. Dropping it would mean a container
# that cannot apply its own schema.
COPY package.json package-lock.json ./
RUN npm ci

# Source, copied path by path rather than with `COPY . .`.
#
# The context is the sibling working tree on a developer machine, so it may well
# contain a `node_modules/` built for the *host* platform and a stale `.next/`.
# Copying those over the layer above would replace Linux binaries — Prisma's query
# engine and Next's SWC among them — with Windows ones, and the failure would show
# up as an unrelated-looking runtime crash. Naming the inputs also means a
# renamed directory in D-Agent fails this build instead of quietly producing an
# image missing half the app.
#
# `.dockerignore` cannot solve this: it is resolved from the context root, which
# belongs to the sibling repository.
COPY app ./app
COPY lib ./lib
COPY prisma ./prisma
COPY public ./public
COPY skills ./skills
COPY next.config.ts tsconfig.json instrumentation.ts proxy.ts ./

# The Prisma client is generated code and is imported by the build, so it has to
# exist before `next build` runs.
RUN npx prisma generate

# A placeholder DATABASE_URL for the build only. Nothing here connects — every
# route handler in D-Agent is `force-dynamic` and its pages are client
# components — but Prisma's schema still requires the variable to be *set*, and a
# real URL baked into an image is a credential in a layer.
RUN DATABASE_URL="postgresql://build:build@127.0.0.1:5432/build?schema=public" npm run build

# The four skills a run drives, pre-installed where the CLI reads them.
#
# D-Agent does not ship its skills to `~/.claude/skills` itself — the Settings
# page has an installer that copies them there, and on a developer machine that
# directory already exists. In a container it starts empty, and a run whose skill
# is missing does not fail fast: the CLI answers `Unknown command:
# /implement-ticket-v3` partway in, after spending tokens.
#
# Copied into the image rather than done by hand after start-up, because
# /root/.claude is a named volume and Docker seeds a *fresh* volume from whatever
# the image has at that path. So the first `up` gets working skills, and anything
# installed or edited later survives, since the seed only happens once.
RUN mkdir -p /root/.claude/skills \
 && cp -r ./skills/. /root/.claude/skills/

# Start-up: apply migrations, then serve.
#
# `migrate deploy` and never `migrate dev`: deploy applies committed migrations
# and stops on drift, whereas dev is free to reset the database to make the
# schema match. On a volume holding real runs, that is the difference between a
# failed start and lost data.
#
# Written as a file rather than a `CMD sh -c "a && b"` so the exec form can hand
# PID 1 to node — a shell parent swallows SIGTERM and turns every `docker compose
# down` into a ten-second kill.
RUN printf '%s\n' \
  '#!/bin/sh' \
  'set -e' \
  'echo "[dagent] applying migrations…"' \
  'npx prisma migrate deploy' \
  'echo "[dagent] starting Next on :3000"' \
  'exec npm run start -- --hostname 0.0.0.0 --port 3000' \
  > /usr/local/bin/dagent-entrypoint.sh \
 && chmod +x /usr/local/bin/dagent-entrypoint.sh

EXPOSE 3000
CMD ["/usr/local/bin/dagent-entrypoint.sh"]
