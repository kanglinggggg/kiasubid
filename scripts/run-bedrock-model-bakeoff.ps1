[CmdletBinding()]
param(
    [string[]]$Models = @(
        "amazon.nova-lite-v1:0",
        "amazon.nova-micro-v1:0",
        "us.amazon.nova-2-lite-v1:0"
    )
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}
if ($Models.Count -lt 2) {
    throw "Provide at least two cheap on-demand model IDs for a bake-off."
}
if ($Models | Where-Object { $_ -match '(?i)provisioned|throughput' }) {
    throw "Provisioned Bedrock resources are forbidden."
}

$outputDirectory = Join-Path $projectRoot "data\evaluation\model_bakeoff"
Push-Location (Join-Path $projectRoot "backend")
try {
    & $pythonPath -m evaluation.bakeoff @Models --output-dir $outputDirectory
    if ($LASTEXITCODE -ne 0) { throw "Known-regression model bake-off failed." }
}
finally {
    Pop-Location
}
