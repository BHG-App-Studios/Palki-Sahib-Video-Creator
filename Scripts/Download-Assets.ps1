<#
.SYNOPSIS
    Downloads private pipeline assets from the companion GitHub repo.

.DESCRIPTION
    Clones the private BHG-App-Studios/Palki-Sahib-Video-Creator-Assets repo
    and copies its contents into the main pipeline repo at the correct paths.

    Authentication uses a GitHub Personal Access Token (PAT) from the
    ASSETS_GITHUB_TOKEN environment variable (set as a GitHub Actions secret).

    The private repo mirrors the folder structure the pipeline expects:
        Scripts/, Publish-Scripts/, Background-Videos/, Shabads/,
        Fonts/, Firefox-Setup/, Samples/, logo.png

    All network operations are retried up to 5 times with exponential
    back-off.  If the clone fails after all retries, the run is failed
    so the admin-failure notification fires.

.PARAMETER Destination
    Root directory where assets are placed.  Defaults to the repo root
    (one level above the Scripts folder).
#>
[CmdletBinding()]
param(
    [string]$Destination = (Split-Path $PSScriptRoot)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Configuration ──────────────────────────────────────────────────────────
$AssetsRepo    = 'https://github.com/BHG-App-Studios/Palki-Sahib-Video-Creator-Assets.git'
$Token         = $env:ASSETS_GITHUB_TOKEN
$MaxAttempts   = 5
$BaseDelaySec  = 3     # exponential back-off: 3 → 6 → 12 → 24 → 48
$TempCloneDir  = Join-Path $Destination '_assets-clone-temp'

if (-not $Token) {
    throw 'Environment variable ASSETS_GITHUB_TOKEN is not set. Add it as a GitHub Actions secret.'
}

# Build the authenticated clone URL (token embedded, never logged).
$authUrl = $AssetsRepo -replace 'https://', "https://x-access-token:${Token}@"

# ── Helper: retry wrapper ──────────────────────────────────────────────────
function Invoke-WithRetry {
    param(
        [Parameter(Mandatory)][string]$OperationName,
        [Parameter(Mandatory)][scriptblock]$Action
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        try {
            return (& $Action)
        } catch {
            $errorMsg = $_.Exception.Message
            if ($attempt -eq $MaxAttempts) {
                Write-Host "   ❌ $OperationName failed after $MaxAttempts attempts. Last error: $errorMsg"
                throw $_
            }
            $delay = $BaseDelaySec * [math]::Pow(2, $attempt - 1)
            Write-Host "   ⚠️  $OperationName failed (attempt $attempt/$MaxAttempts): $errorMsg"
            Write-Host "      Retrying in ${delay}s..."
            Start-Sleep -Seconds $delay
        }
    }
}

# ── 1. Clone the private assets repo (with retry) ─────────────────────────
# Clean up any leftover temp directory from a previous failed run.
if (Test-Path $TempCloneDir) {
    Write-Host '🧹 Removing leftover temp clone directory...'
    Remove-Item $TempCloneDir -Recurse -Force
}

Write-Host '📦 Cloning private assets repo...'
Invoke-WithRetry -OperationName 'Git clone' -Action {
    # Shallow clone (depth 1) — we only need the latest files, not history.
    # This saves bandwidth and time, especially with large video/audio files.
    $output = git clone --depth 1 $authUrl $TempCloneDir 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git clone failed (exit code $LASTEXITCODE): $output"
    }
}

Write-Host "   ✅ Clone successful.`n"

# ── 2. Copy assets into the pipeline repo ──────────────────────────────────
Write-Host '📂 Copying assets to pipeline repo...'
$copied  = 0
$skipped = 0

# Get all files from the clone, excluding the .git directory.
$allFiles = Get-ChildItem -Path $TempCloneDir -Recurse -File |
    Where-Object { $_.FullName -notlike "*\.git\*" }

$totalFiles = $allFiles.Count
Write-Host "   Found $totalFiles file(s) to copy.`n"

foreach ($file in $allFiles) {
    # Build the relative path from the clone root.
    $relativePath = $file.FullName.Substring($TempCloneDir.Length).TrimStart('\', '/')
    $targetPath   = Join-Path $Destination $relativePath
    $targetDir    = Split-Path $targetPath

    # Ensure parent directory exists.
    if ($targetDir -and -not (Test-Path $targetDir)) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }

    # Copy the file (overwrite if already exists from a previous run).
    try {
        Copy-Item -Path $file.FullName -Destination $targetPath -Force
        Write-Host "   ✅ $relativePath"
        $copied++
    } catch {
        Write-Warning "   ❌ Failed to copy ${relativePath}: $_"
        throw "Failed to copy asset file: $relativePath"
    }
}

# ── 3. Cleanup temp clone directory ────────────────────────────────────────
Write-Host "`n🧹 Cleaning up temp clone directory..."
try {
    Remove-Item $TempCloneDir -Recurse -Force
} catch {
    Write-Warning "Could not remove temp directory ${TempCloneDir}: $_"
    # Non-fatal: the pipeline can still run.
}

# ── 4. Summary ─────────────────────────────────────────────────────────────
Write-Host ''
Write-Host '════════════════════════════════════════════════════════════════'
Write-Host '   📊 Asset Download Summary'
Write-Host "      Total files : $totalFiles"
Write-Host "      Copied      : $copied"
Write-Host '════════════════════════════════════════════════════════════════'
Write-Host ''

if ($copied -ne $totalFiles) {
    throw "Only $copied of $totalFiles assets were copied. The pipeline cannot continue."
}

Write-Host '✅ All assets downloaded successfully. Pipeline is ready to run.'
