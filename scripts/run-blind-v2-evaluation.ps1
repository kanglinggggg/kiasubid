[CmdletBinding()]
param(
    [string]$Output = "data\evaluation\blind_v2_report.json"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$caseDirectory = Join-Path $projectRoot "backend\evaluation\cases\blind_v2"
$caseFiles = @(Get-ChildItem -LiteralPath $caseDirectory -Filter "*.json" -File)

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}
if ($caseFiles.Count -eq 0) {
    throw "No sealed blind-v2 JSON cases found. A teammate must add ground truth before any run."
}

$outputPath = if ([IO.Path]::IsPathRooted($Output)) {
    $Output
} else {
    Join-Path $projectRoot $Output
}

Push-Location (Join-Path $projectRoot "backend")
try {
    & $pythonPath -m evaluation --partition blind-v2 --output $outputPath
    if ($LASTEXITCODE -ne 0) { throw "Blind-v2 interpretation evaluation failed." }
}
finally {
    Pop-Location
}

Write-Host "Blind-v2 evaluation report: $outputPath"
