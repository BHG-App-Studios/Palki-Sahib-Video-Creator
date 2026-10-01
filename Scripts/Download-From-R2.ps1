<#
.SYNOPSIS
    Downloads private pipeline assets from Cloudflare R2 into the repo.

.DESCRIPTION
    Calls the Cloudflare Worker that fronts the R2 bucket.  Authentication
    uses an X-Auth-Key header whose value comes from the R2_ASSETS_KEY
    environment variable (set as a GitHub Actions secret).

    The worker returns a flat JSON list of all object keys when GET / is
    called.  Each key mirrors the repo-relative path (e.g.
    "Scripts/01_download_stream.py", "Shabads/1/1.mp3", "logo.png").

    Files are downloaded to -Destination (defaults to the repo root).
    Existing files are skipped unless -Force is specified.

    Every network operation (listing and per-file download) is retried up
    to 5 times with exponential back-off before the run is failed.  A
    failed run triggers the admin-failure notification in the workflow.

.PARAMETER Destination
    Root directory where files are placed.  Defaults to the repo root
    (one level above the Scripts folder).

.PARAMETER Force
    Re-download every file even if it already exists locally.
#>
[CmdletBinding()]
param(
    [string]$Destination = (Split-Path $PSScriptRoot),
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ── Configuration ──────────────────────────────────────────────────────────
$WorkerBaseUrl   = 'https://palki-sahib-video-creator.gssingh0897.workers.dev'
$AuthKey         = $env:R2_ASSETS_KEY
$MaxAttempts     = 5
$BaseDelaySec    = 3     # exponential back-off: 3 → 6 → 12 → 24 → 48

if (-not $AuthKey) {
    throw 'Environment variable R2_ASSETS_KEY is not set. Add it as a GitHub Actions secret.'
}

$headers = @{ 'X-Auth-Key' = $AuthKey }

# ── Helper: retry wrapper ──────────────────────────────────────────────────
function Invoke-WithRetry {
    <#
    .SYNOPSIS
        Executes a script block with retry logic and exponential back-off.
    #>
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

# ── 1. Fetch the asset list from R2 (with retry) ──────────────────────────
Write-Host '📦 Fetching asset list from R2...'
$listResponse = Invoke-WithRetry -OperationName 'Fetch asset list' -Action {
    $response = Invoke-RestMethod -Uri $WorkerBaseUrl -Headers $headers -Method Get
    # Validate the response is a non-empty array.
    if ($response -isnot [System.Collections.IEnumerable] -or $response.Count -eq 0) {
        throw 'R2 bucket returned an empty or invalid asset list.'
    }
    return $response
}

$totalAssets = $listResponse.Count
Write-Host "   Found $totalAssets asset(s) in R2.`n"

# ── 2. Download each file (with per-file retry) ───────────────────────────
$downloaded  = 0
$skipped     = 0
$failedFiles = [System.Collections.Generic.List[string]]::new()

foreach ($key in $listResponse) {
    # Build the local path from the R2 key (which mirrors repo structure).
    $localPath = Join-Path $Destination ($key -replace '/', '\')
    $localDir  = Split-Path $localPath

    # Skip if already present (unless -Force).
    if (-not $Force -and (Test-Path $localPath)) {
        $skipped++
        continue
    }

    # Ensure parent directory exists.
    if ($localDir -and -not (Test-Path $localDir)) {
        New-Item -ItemType Directory -Path $localDir -Force | Out-Null
    }

    $fileUrl = "$WorkerBaseUrl/$key"
    try {
        Write-Host "   ⬇️  $key"
        Invoke-WithRetry -OperationName "Download $key" -Action {
            Invoke-WebRequest -Uri $fileUrl -Headers $headers -OutFile $localPath -UseBasicParsing

            # Integrity check: make sure the file was actually written and is not empty.
            if (-not (Test-Path $localPath)) {
                throw "File was not created on disk: $localPath"
            }
            $fileSize = (Get-Item $localPath).Length
            if ($fileSize -eq 0) {
                Remove-Item $localPath -Force -ErrorAction SilentlyContinue
                throw "Downloaded file is 0 bytes (corrupt or empty): $key"
            }
        }
        $downloaded++
    } catch {
        Write-Warning "   ❌ FAILED after $MaxAttempts attempts: $key — $($_.Exception.Message)"
        # Clean up any partial/corrupt file.
        if (Test-Path $localPath) {
            Remove-Item $localPath -Force -ErrorAction SilentlyContinue
        }
        $failedFiles.Add($key)
    }
}

# ── 3. Summary & final verdict ─────────────────────────────────────────────
Write-Host ''
Write-Host '════════════════════════════════════════════════════════════════'
Write-Host "   📊 Asset Download Summary"
Write-Host "      Total in R2 : $totalAssets"
Write-Host "      Downloaded  : $downloaded"
Write-Host "      Skipped     : $skipped (already exist)"
Write-Host "      Failed      : $($failedFiles.Count)"
Write-Host '════════════════════════════════════════════════════════════════'

if ($failedFiles.Count -gt 0) {
    Write-Host ''
    Write-Host '❌ The following assets could not be downloaded:'
    foreach ($f in $failedFiles) {
        Write-Host "      • $f"
    }
    Write-Host ''
    # Throwing here fails the GitHub Actions step, which triggers the
    # "Notify admin app of failed run" step in the workflow.
    throw "$($failedFiles.Count) asset(s) failed to download after $MaxAttempts retries each. The pipeline cannot continue without these files."
}

Write-Host ''
Write-Host '✅ All assets downloaded successfully. Pipeline is ready to run.'
