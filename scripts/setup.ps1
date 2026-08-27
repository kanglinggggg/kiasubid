[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot ".uv-cache"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv is required. Install it from https://docs.astral.sh/uv/ and rerun this script."
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Node.js and npm are required. Install Node.js 20 or newer and rerun this script."
}

if (-not (Test-Path (Join-Path $projectRoot ".env"))) {
    Copy-Item -LiteralPath (Join-Path $projectRoot ".env.example") -Destination (Join-Path $projectRoot ".env")
    Write-Host "Created .env from .env.example (live-provider credentials remain blank)."
}

Push-Location $projectRoot
try {
    uv sync --all-groups --locked
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed with exit code $LASTEXITCODE" }

    Push-Location (Join-Path $projectRoot "frontend")
    try {
        npm.cmd ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

Write-Host "Local dependencies are ready."
