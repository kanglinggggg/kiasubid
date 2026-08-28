[CmdletBinding()]
param(
    [string]$ModelId,
    [switch]$PromptValidatedJson,
    [switch]$SkipBlindEvaluation
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $projectRoot ".env"
$officialRegion = "us-east-1"
$allowedEnvNames = @(
    "LLM_PROVIDER",
    "AWS_PROFILE",
    "AWS_DEFAULT_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "BEDROCK_MODEL_ID",
    "BEDROCK_STRUCTURED_OUTPUT",
    "LLM_MAX_RETRIES"
)

function Import-AllowedDotEnv {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { continue }
        $name = $Matches[1]
        if ($name -notin $allowedEnvNames) { continue }
        $value = $Matches[2].Trim()
        if (
            $value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
             ($value.StartsWith("'") -and $value.EndsWith("'")))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        if (-not [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Invoke-AwsJson {
    param([string[]]$Arguments)
    $raw = & $script:awsPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "AWS CLI command failed. Refresh the temporary sandbox credentials and retry."
    }
    return (($raw | Out-String) | ConvertFrom-Json)
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Python environment is missing. Run scripts\setup.ps1 first."
}

Import-AllowedDotEnv -Path $envPath

$configuredRegion = [Environment]::GetEnvironmentVariable("AWS_DEFAULT_REGION", "Process")
if ($configuredRegion -and $configuredRegion -ne $officialRegion) {
    throw "AWS_DEFAULT_REGION must be $officialRegion, not $configuredRegion."
}
[Environment]::SetEnvironmentVariable("AWS_DEFAULT_REGION", $officialRegion, "Process")
[Environment]::SetEnvironmentVariable("AWS_REGION", $officialRegion, "Process")
[Environment]::SetEnvironmentVariable("LLM_PROVIDER", "bedrock", "Process")
if ($PromptValidatedJson) {
    [Environment]::SetEnvironmentVariable("BEDROCK_STRUCTURED_OUTPUT", "false", "Process")
} elseif (-not [Environment]::GetEnvironmentVariable("BEDROCK_STRUCTURED_OUTPUT", "Process")) {
    [Environment]::SetEnvironmentVariable("BEDROCK_STRUCTURED_OUTPUT", "true", "Process")
}
$nativeStructuredOutput = (
    [Environment]::GetEnvironmentVariable("BEDROCK_STRUCTURED_OUTPUT", "Process") -ne "false"
)

if ($ModelId) {
    [Environment]::SetEnvironmentVariable("BEDROCK_MODEL_ID", $ModelId, "Process")
}
$selectedModel = [Environment]::GetEnvironmentVariable("BEDROCK_MODEL_ID", "Process")

$awsCommand = Get-Command aws -ErrorAction SilentlyContinue
if ($awsCommand) {
    $script:awsPath = $awsCommand.Source
} else {
    $fallbackAwsPath = "C:\Program Files\Amazon\AWSCLIV2\aws.exe"
    if (-not (Test-Path -LiteralPath $fallbackAwsPath)) {
        throw "AWS CLI is not installed or available on PATH."
    }
    $script:awsPath = $fallbackAwsPath
}

$accessKeyPresent = [bool][Environment]::GetEnvironmentVariable("AWS_ACCESS_KEY_ID", "Process")
$secretKeyPresent = [bool][Environment]::GetEnvironmentVariable("AWS_SECRET_ACCESS_KEY", "Process")
$sessionTokenPresent = [bool][Environment]::GetEnvironmentVariable("AWS_SESSION_TOKEN", "Process")
$profilePresent = [bool][Environment]::GetEnvironmentVariable("AWS_PROFILE", "Process")
if (-not $profilePresent -and -not ($accessKeyPresent -and $secretKeyPresent -and $sessionTokenPresent)) {
    throw "Temporary AWS credentials are unavailable or incomplete. No AWS call was made."
}

Write-Host "1/6 Verifying temporary AWS identity..."
$identity = Invoke-AwsJson -Arguments @(
    "sts", "get-caller-identity", "--region", $officialRegion, "--output", "json"
)
Write-Host "Authenticated sandbox identity: account $($identity.Account); ARN $($identity.Arn)"
Write-Host "Region verified: $officialRegion"

Write-Host "2/6 Inspecting Bedrock's current text-model catalogue..."
$catalog = Invoke-AwsJson -Arguments @(
    "bedrock", "list-foundation-models", "--region", $officialRegion,
    "--by-output-modality", "TEXT", "--output", "json"
)
$cheapNamePattern = '(?i)(nova\s+(micro|lite)|claude.*haiku)'
$cheapModels = @(
    $catalog.modelSummaries |
        Where-Object {
            $_.modelLifecycle.status -eq "ACTIVE" -and
            $_.inferenceTypesSupported -contains "ON_DEMAND" -and
            ("$($_.modelName) $($_.modelId)" -match $cheapNamePattern)
        } |
        Select-Object modelId, modelName, providerName, inferenceTypesSupported
)

$profiles = $null
try {
    $profiles = Invoke-AwsJson -Arguments @(
        "bedrock", "list-inference-profiles", "--region", $officialRegion,
        "--type-equals", "SYSTEM_DEFINED", "--output", "json"
    )
} catch {
    Write-Warning "System inference profiles could not be listed; foundation models were listed successfully."
}
$cheapProfiles = @(
    $profiles.inferenceProfileSummaries |
        Where-Object {
            $_.status -eq "ACTIVE" -and
            ("$($_.inferenceProfileName) $($_.inferenceProfileId)" -match $cheapNamePattern)
        } |
        Select-Object inferenceProfileId, inferenceProfileName, type, status
)

Write-Host "Cheap on-demand foundation-model candidates discovered:"
if ($cheapModels.Count) { $cheapModels | Format-Table -AutoSize } else { Write-Host "  None" }
Write-Host "Cheap system inference-profile candidates discovered:"
if ($cheapProfiles.Count) { $cheapProfiles | Format-Table -AutoSize } else { Write-Host "  None" }

if (-not $selectedModel) {
    throw "BEDROCK_MODEL_ID is blank. Select one discovered cheap on-demand model or system inference profile, then rerun."
}
if ($selectedModel -match '(?i)provisioned|provisioned-model|provisioned-throughput') {
    throw "Provisioned Bedrock resources are forbidden for this validation."
}
$selectedFoundation = $cheapModels | Where-Object { $_.modelId -eq $selectedModel }
$selectedProfile = $cheapProfiles | Where-Object { $_.inferenceProfileId -eq $selectedModel }
if (-not $selectedFoundation -and -not $selectedProfile) {
    throw "The configured BEDROCK_MODEL_ID is not one of the discovered cheap on-demand candidates."
}

if (-not $nativeStructuredOutput) {
    Write-Host "3/6 Running prompted JSON with strict local Pydantic validation..."
} else {
    Write-Host "3/6 Running one native Bedrock JSON-schema structured-output inference..."
}
Write-Host "4/6 Running Bedrock -> R17 -> deterministic FEASIBLE to RECOVERABLE validation..."
Push-Location (Join-Path $projectRoot "backend")
try {
    & $pythonPath -m evaluation.aws_post_approval
    if ($LASTEXITCODE -ne 0) { throw "Bedrock smoke or R17 validation failed." }

    Write-Host "5/6 Running the known GeBIZ-derived live-model regression..."
    & $pythonPath -m evaluation --partition regression `
        --output (Join-Path $projectRoot "data\evaluation\live_regression_report.json")
    if ($LASTEXITCODE -ne 0) { throw "Live-model regression failed." }

    Write-Host "6/6 Checking for teammate-supplied blind cases..."
    $blindDirectory = Join-Path $projectRoot "backend\evaluation\cases\blind"
    $blindCases = @(Get-ChildItem -LiteralPath $blindDirectory -Filter "*.json" -File)
    if ($blindCases.Count -gt 0 -and -not $SkipBlindEvaluation) {
        & $pythonPath -m evaluation --partition blind `
            --output (Join-Path $projectRoot "data\evaluation\blind_report.json")
        if ($LASTEXITCODE -ne 0) { throw "Blind live-model evaluation failed." }
    } elseif ($blindCases.Count -eq 0) {
        Write-Host "No blind cases are present; no unseen performance is claimed."
    } else {
        Write-Host "Blind evaluation explicitly skipped."
    }
}
finally {
    Pop-Location
}

Write-Host "AWS post-approval validation completed without using provisioned throughput."
