[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runDirectory = Join-Path $projectRoot "data\run"

foreach ($service in @("frontend", "backend")) {
    $pidPath = Join-Path $runDirectory "$service.pid"
    if (-not (Test-Path $pidPath)) { continue }
    $servicePid = [int](Get-Content -LiteralPath $pidPath -Raw)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $servicePid" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -like "*GeBIZ*") {
        & taskkill.exe /PID $servicePid /T /F | Out-Null
        Write-Host "Stopped $service (PID $servicePid)."
    }
    elseif ($process) {
        Write-Warning "PID $servicePid no longer belongs to GeBIZ; it was not stopped."
    }
    Remove-Item -LiteralPath $pidPath -Force
}
