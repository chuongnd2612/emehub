#!/usr/bin/env bash
# Drive the whole suite's compose project.
#
#   ./suite.sh up -d --build
#   ./suite.sh ps
#   ./suite.sh logs -f dagent-web
#   ./suite.sh down
#
# It exists for one reason: docker-compose.suite.yml pulls services out of three
# repositories, and compose resolves `${…}` against the project's environment
# rather than the file each service came from — so all three .env files have to be
# named on every command. Typing that by hand is how one gets left off, and a
# missing --env-file does not fail loudly: `${QAGENT_HUB_JWT_SECRET:-}` simply
# becomes empty and single sign-on stops working for reasons nothing reports.
#
# Every argument is passed straight through to `docker compose`.
set -euo pipefail
cd "$(dirname "$0")"
exec docker compose \
  -f docker-compose.suite.yml \
  --env-file .env \
  --env-file dagent/.env \
  --env-file ../q-agent/.env \
  "$@"
