[CmdletBinding()]
param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $projectRoot "data\run"
$logDirectory = Join-Path $projectRoot "data\logs"
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not $SkipInstall) {
    & (Join-Path $PSScriptRoot "setup.ps1")
}
if (-not (Test-Path $pythonPath)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}

New-Item -ItemType Directory -Force -Path $runDirectory, $logDirectory | Out-Null

function Test-Endpoint {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Wait-Endpoint {
    param([string]$Url, [string]$Name)
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-Endpoint $Url) { return }
        Start-Sleep -Milliseconds 500
    }
    throw "$Name did not become ready at $Url. Check data\logs for details."
}

if (-not (Test-Endpoint "http://127.0.0.1:8000/api/health")) {
    $backend = Start-Process -FilePath $pythonPath `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app",
            "--app-dir", (Join-Path $projectRoot "backend"),
            "--host", "127.0.0.1", "--port", "8000"
        ) `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput (Join-Path $logDirectory "backend.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "backend.err.log") `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath (Join-Path $runDirectory "backend.pid") -Value $backend.Id
}
Wait-Endpoint "http://127.0.0.1:8000/api/health" "FastAPI"

if (-not (Test-Endpoint "http://127.0.0.1:5173")) {
    $frontend = Start-Process -FilePath "cmd.exe" `
        -ArgumentList @(
            "/d", "/c",
            "npm.cmd --prefix $projectRoot\frontend run dev -- --host 127.0.0.1"
        ) `
        -WorkingDirectory (Join-Path $projectRoot "frontend") `
        -RedirectStandardOutput (Join-Path $logDirectory "frontend.out.log") `
        -RedirectStandardError (Join-Path $logDirectory "frontend.err.log") `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -LiteralPath (Join-Path $runDirectory "frontend.pid") -Value $frontend.Id
}
Wait-Endpoint "http://127.0.0.1:5173" "Vite"

Write-Host "GeBIZ BidOps is ready:"
Write-Host "  App: http://127.0.0.1:5173"
Write-Host "  API: http://127.0.0.1:8000/docs"
Write-Host "  Logs: $logDirectory"
