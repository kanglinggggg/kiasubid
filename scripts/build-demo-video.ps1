[CmdletBinding()]
param(
    [string]$Voice = "Microsoft Hazel Desktop",
    [int]$VoiceRate = 1,
    [string]$AppUrl = "http://127.0.0.1:5173/",
    [string]$SceneFile = "docs\video\demo-scenes.json",
    [string]$OutputName = "gebiz-bidops-demo-draft.mp4",
    [string]$PlaywrightPackageDir = $env:PLAYWRIGHT_PACKAGE_DIR,
    [switch]$NoNarration
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$sceneFile = Join-Path $projectRoot $SceneFile
$outputDir = Join-Path $projectRoot "output\demo-video"
$workDir = Join-Path $outputDir "work"
$finalVideo = Join-Path $outputDir $OutputName
$thumbnail = Join-Path $outputDir "gebiz-bidops-demo-thumbnail.png"

New-Item -ItemType Directory -Force -Path $workDir | Out-Null

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 5
    $frontend = Invoke-WebRequest -Uri $AppUrl -UseBasicParsing -TimeoutSec 5
} catch {
    throw "BidOps must be running on localhost before the video can be built. Run scripts\start.ps1 first."
}

if ($health.status -ne "ok" -or $frontend.StatusCode -ne 200) {
    throw "BidOps health check failed."
}

$node = (Get-Command node -ErrorAction Stop).Source
$playwrightCandidates = @()
if ($PlaywrightPackageDir) {
    $playwrightCandidates += $PlaywrightPackageDir
}
$playwrightCandidates += @(
    (Join-Path $projectRoot "frontend\node_modules\playwright-core"),
    (Join-Path $projectRoot "node_modules\playwright"),
    (Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright")
)
$playwrightPackage = $playwrightCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -First 1
if (-not $playwrightPackage) {
    throw "Playwright was not found. Run npm install in frontend or pass -PlaywrightPackageDir."
}

$ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
if (-not $ffmpegCommand) {
    $wingetFfmpeg = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\ffmpeg.exe"
    if (Test-Path -LiteralPath $wingetFfmpeg) {
        $ffmpeg = $wingetFfmpeg
    } else {
        $wingetPackageRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
        $ffmpeg = Get-ChildItem -LiteralPath $wingetPackageRoot -Filter "ffmpeg.exe" -File -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match "Gyan\.FFmpeg" } |
            Select-Object -ExpandProperty FullName -First 1
        if (-not $ffmpeg) {
            throw "A full FFmpeg build is required for H.264 and AAC output. Install Gyan.FFmpeg with winget."
        }
    }
} else {
    $ffmpeg = $ffmpegCommand.Source
}
$ffprobe = Join-Path (Split-Path -Parent $ffmpeg) "ffprobe.exe"
if (-not (Test-Path -LiteralPath $ffprobe)) {
    throw "FFprobe was not found beside FFmpeg."
}

$chromeCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$chrome = $chromeCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    throw "Chrome or Edge was not found for the screen capture."
}

$scenes = Get-Content -Raw -LiteralPath $sceneFile | ConvertFrom-Json
$ttsScript = Join-Path $workDir "synthesize-scene.ps1"
@'
param(
    [Parameter(Mandatory = $true)][string]$OutputPath,
    [Parameter(Mandatory = $true)][string]$Text,
    [Parameter(Mandatory = $true)][string]$Voice,
    [Parameter(Mandatory = $true)][int]$Rate
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.SelectVoice($Voice)
    $synth.Rate = $Rate
    $synth.Volume = 100
    $synth.SetOutputToWaveFile($OutputPath)
    $synth.Speak($Text)
} finally {
    $synth.Dispose()
}
'@ | Set-Content -LiteralPath $ttsScript -Encoding UTF8

if (-not $NoNarration) {
    $paddedFiles = @()
    for ($index = 0; $index -lt $scenes.Count; $index += 1) {
        $number = ($index + 1).ToString("00")
        $rawAudio = Join-Path $workDir "scene-$number-raw.wav"
        $paddedAudio = Join-Path $workDir "scene-$number.wav"
        $durationSeconds = [math]::Round([double]$scenes[$index].duration_ms / 1000, 3)

        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $ttsScript `
            -OutputPath $rawAudio `
            -Text ([string]$scenes[$index].narration) `
            -Voice $Voice `
            -Rate $VoiceRate
        if ($LASTEXITCODE -ne 0) {
            throw "Narration synthesis failed for scene $number."
        }

        $spokenSeconds = [double](& $ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 $rawAudio)
        if ($spokenSeconds -gt $durationSeconds) {
            throw "Narration for scene $number is $([math]::Round($spokenSeconds, 2))s but the scene is ${durationSeconds}s. Increase the scene duration or shorten the narration."
        }

        & $ffmpeg -hide_banner -loglevel error -y `
            -i $rawAudio `
            -af "apad=whole_dur=$durationSeconds" `
            -t $durationSeconds `
            -ar 48000 -ac 2 -c:a pcm_s16le $paddedAudio
        if ($LASTEXITCODE -ne 0) {
            throw "Audio padding failed for scene $number."
        }
        $paddedFiles += $paddedAudio
    }

    $concatFile = Join-Path $workDir "narration-concat.txt"
    $concatLines = $paddedFiles | ForEach-Object {
        "file '" + ($_.Replace("\", "/").Replace("'", "'\''")) + "'"
    }
    $concatLines | Set-Content -LiteralPath $concatFile -Encoding ascii
    $narration = Join-Path $workDir "narration.wav"
    & $ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i $concatFile -c copy $narration
    if ($LASTEXITCODE -ne 0) {
        throw "Narration assembly failed."
    }
}

$env:PLAYWRIGHT_PACKAGE_DIR = $playwrightPackage
$env:CHROME_PATH = $chrome
$env:DEMO_APP_URL = $AppUrl
$env:DEMO_SCENES_PATH = $sceneFile
$env:DEMO_VIDEO_WORK_DIR = $workDir
& $node (Join-Path $projectRoot "scripts\capture-demo-video.mjs")
if ($LASTEXITCODE -ne 0) {
    throw "Browser capture failed."
}

$capture = Join-Path $workDir "bidops-demo-capture.webm"
if ($NoNarration) {
    & $ffmpeg -hide_banner -loglevel error -y `
        -i $capture -map 0:v:0 -an `
        -vf "scale=1280:720:flags=lanczos,format=yuv420p" `
        -c:v libx264 -preset medium -crf 20 `
        -movflags +faststart $finalVideo
} else {
    & $ffmpeg -hide_banner -loglevel error -y `
        -i $capture -i $narration `
        -map 0:v:0 -map 1:a:0 `
        -vf "scale=1280:720:flags=lanczos,format=yuv420p" `
        -c:v libx264 -preset medium -crf 20 `
        -c:a aac -b:a 160k -af apad -shortest `
        -movflags +faststart $finalVideo
}
if ($LASTEXITCODE -ne 0) {
    throw "Final MP4 encoding failed."
}

$finalDuration = [double](& $ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 $finalVideo)
if ($finalDuration -gt 300) {
    throw "The generated video is $([math]::Round($finalDuration, 2)) seconds, exceeding the 5-minute submission limit."
}

& $ffmpeg -hide_banner -loglevel error -y -ss 18 -i $finalVideo -frames:v 1 $thumbnail
if ($LASTEXITCODE -ne 0) {
    throw "Thumbnail generation failed."
}

$videoInfo = Get-Item -LiteralPath $finalVideo
Write-Output "Demo video created: $($videoInfo.FullName)"
Write-Output "Size: $([math]::Round($videoInfo.Length / 1MB, 2)) MB"
Write-Output "Duration: $([math]::Round($finalDuration, 2)) seconds"
Write-Output "Interpretation shown in this recording: Demo fallback"
Write-Output "Browser capture log: $(Join-Path $workDir 'browser-errors.txt')"
