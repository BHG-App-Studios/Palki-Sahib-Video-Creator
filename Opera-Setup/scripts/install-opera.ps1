[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Workspace
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$sourceArchive = Join-Path $Workspace 'Opera\Opera Software.zip'
$installCommandFile = Join-Path $Workspace 'Opera\install_Opera.txt'
$pinnedOperaVersion = '133.0.5932.85'
$roamingDirectory = [Environment]::GetFolderPath(
    [Environment+SpecialFolder]::ApplicationData
)
$movedArchive = Join-Path $roamingDirectory 'Opera Software.zip'

if (-not (Test-Path -LiteralPath $sourceArchive -PathType Leaf)) {
    throw "Opera archive was not found: $sourceArchive"
}

if (-not (Test-Path -LiteralPath $installCommandFile -PathType Leaf)) {
    throw "Opera install command file was not found: $installCommandFile"
}

$archiveHeader = Get-Content -LiteralPath $sourceArchive -TotalCount 1 -ErrorAction Stop
if ($archiveHeader -match '^version https://git-lfs.github.com/spec/') {
    throw 'Opera Software.zip is a Git LFS pointer instead of the real archive.'
}

Write-Host "Moving archive to $movedArchive"
Move-Item -LiteralPath $sourceArchive -Destination $movedArchive -Force

Write-Host "Extracting archive into $roamingDirectory"
Expand-Archive -LiteralPath $movedArchive -DestinationPath $roamingDirectory -Force

$expectedProfile = Join-Path $roamingDirectory 'Opera Software\Opera Stable'
if (-not (Test-Path -LiteralPath $expectedProfile -PathType Container)) {
    throw "Expected Opera profile was not extracted: $expectedProfile"
}

$installCommand = (Get-Content -LiteralPath $installCommandFile -Raw).Trim()
$expectedInstallCommand = "winget install -e --id Opera.Opera --version $pinnedOperaVersion"
if ($installCommand -ne $expectedInstallCommand) {
    throw "Unexpected command in install_Opera.txt: $installCommand"
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'winget is not available on this Windows runner.'
}

$wingetArguments = @(
    'install'
    '--exact'
    '--id', 'Opera.Opera'
    '--version', $pinnedOperaVersion
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
    throw "Opera installation failed with winget exit code $($process.ExitCode)."
}

$operaCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Opera\opera.exe')
    (Join-Path $env:ProgramFiles 'Opera\opera.exe')
)

if (${env:ProgramFiles(x86)}) {
    $operaCandidates += Join-Path ${env:ProgramFiles(x86)} 'Opera\opera.exe'
}

$operaExecutable = $operaCandidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

if (-not $operaExecutable) {
    throw 'winget completed, but opera.exe was not found in the expected install locations.'
}

$operaVersion = (Get-Item -LiteralPath $operaExecutable).VersionInfo.ProductVersion
Write-Host "Opera installed successfully: $operaExecutable"
Write-Host "Opera version: $operaVersion"

if ($env:GITHUB_OUTPUT) {
    "opera_executable=$operaExecutable" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "opera_version=$operaVersion" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}
