#!/usr/bin/env pwsh
# Drive the whole suite's compose project. See suite.sh for why it exists.
#
#   .\suite.ps1 up -d --build
#   .\suite.ps1 ps
#   .\suite.ps1 logs -f dagent-web
#   .\suite.ps1 down
#
# Every argument is passed straight through to `docker compose`.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    docker compose `
        -f docker-compose.suite.yml `
        --env-file .env `
        --env-file dagent/.env `
        --env-file ../q-agent/.env `
        @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
