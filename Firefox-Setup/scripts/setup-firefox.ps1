[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$sourceArchive = Join-Path $Workspace 'Firefox\Firefox.zip'

if (-not (Test-Path -LiteralPath $sourceArchive -PathType Leaf)) {
    throw "Firefox profile archive was not found: $sourceArchive"
}

$archiveHeader = Get-Content -LiteralPath $sourceArchive -TotalCount 1 -ErrorAction Stop
if ($archiveHeader -match '^version https://git-lfs.github.com/spec/') {
    throw 'Firefox.zip is a Git LFS pointer instead of the real archive.'
}

# --- Step 1: Install Firefox if not already present ---

$firefoxCandidates = @(
    (Join-Path $env:ProgramFiles 'Mozilla Firefox\firefox.exe')
)

if (${env:ProgramFiles(x86)}) {
    $firefoxCandidates += Join-Path ${env:ProgramFiles(x86)} 'Mozilla Firefox\firefox.exe'
}

$firefoxExecutable = $firefoxCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

if (-not $firefoxExecutable) {
    Write-Host 'Firefox not found. Installing via winget...'

    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw 'winget is not available on this Windows runner.'
    }

    $wingetArguments = @(
        'install'
        '--exact'
        '--id', 'Mozilla.Firefox'
        '--silent'
        '--accept-package-agreements'
        '--accept-source-agreements'
        '--disable-interactivity'
    )

    Write-Host "Running: winget $($wingetArguments -join ' ')"
    $process = Start-Process `
        -FilePath 'winget.exe' `
        -ArgumentList $wingetArguments `
        -NoNewWindow `
        -Wait `
        -PassThru

    if ($process.ExitCode -ne 0) {
        throw "Firefox installation failed with winget exit code $($process.ExitCode)."
    }

    $firefoxExecutable = $firefoxCandidates |
        Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
        Select-Object -First 1

    if (-not $firefoxExecutable) {
        throw 'winget completed, but firefox.exe was not found in expected locations.'
    }
}
else {
    Write-Host 'Firefox is already installed.'
}

$firefoxVersion = (Get-Item -LiteralPath $firefoxExecutable).VersionInfo.ProductVersion
Write-Host "Firefox executable: $firefoxExecutable"
Write-Host "Firefox version: $firefoxVersion"

# --- Step 2: Extract the backed-up profile over any default profile ---

$roamingDirectory = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::ApplicationData
)
$mozillaDirectory = Join-Path $roamingDirectory 'Mozilla'

New-Item -ItemType Directory -Path $mozillaDirectory -Force | Out-Null

Write-Host "Extracting Firefox profile archive to $mozillaDirectory"
Expand-Archive -LiteralPath $sourceArchive -DestinationPath $mozillaDirectory -Force

$expectedProfilesIni = Join-Path $mozillaDirectory 'Firefox\profiles.ini'
if (-not (Test-Path -LiteralPath $expectedProfilesIni -PathType Leaf)) {
    throw "Expected profiles.ini was not found after extraction: $expectedProfilesIni"
}

Write-Host 'Firefox profile restored successfully.'

if ($env:GITHUB_OUTPUT) {
    "firefox_executable=$firefoxExecutable" |
        Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "firefox_version=$firefoxVersion" |
        Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}
