[CmdletBinding()]
param(
    [switch]$RunLiveEvaluation
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$ruffPath = Join-Path $projectRoot ".venv\Scripts\ruff.exe"

if (-not (Test-Path $pythonPath)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}

Push-Location $projectRoot
try {
    & $ruffPath check backend
    if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Backend tests failed." }

    Push-Location (Join-Path $projectRoot "frontend")
    try {
        npm.cmd run test
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
        npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed." }
    }
    finally {
        Pop-Location
    }

    Push-Location (Join-Path $projectRoot "backend")
    try {
        & $pythonPath -m evaluation.rule_runner --output ..\data\evaluation\deterministic_report.json
        if ($LASTEXITCODE -ne 0) { throw "Deterministic evaluation failed." }
        if ($RunLiveEvaluation) {
            & $pythonPath -m evaluation --partition regression --output ..\data\evaluation\live_report.json
            if ($LASTEXITCODE -ne 0) { throw "Live interpretation evaluation failed." }
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    Pop-Location
}

Write-Host "All requested local checks passed."
