[CmdletBinding()]
param(
    [string]$Output = "data\evaluation\blind_report.json"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$caseDirectory = Join-Path $projectRoot "backend\evaluation\cases\blind"
$caseFiles = @(Get-ChildItem -LiteralPath $caseDirectory -Filter "*.json" -File)

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}
if ($caseFiles.Count -eq 0) {
    throw "No blind JSON cases found in $caseDirectory. Add frozen teammate-authored cases first."
}

$outputPath = if ([IO.Path]::IsPathRooted($Output)) {
    $Output
} else {
    Join-Path $projectRoot $Output
}

Push-Location (Join-Path $projectRoot "backend")
try {
    & $pythonPath -m evaluation --partition blind --output $outputPath
    if ($LASTEXITCODE -ne 0) { throw "Blind interpretation evaluation failed." }
}
finally {
    Pop-Location
}

Write-Host "Blind evaluation report: $outputPath"
