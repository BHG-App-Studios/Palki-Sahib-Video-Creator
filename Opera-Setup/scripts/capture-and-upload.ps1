[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [Parameter(Mandatory = $true)]
    [string]$WorkerUrl,

    [Parameter(Mandatory = $true)]
    [string]$ApiKey
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw 'The CLOUDFLARE_WORKER_API_KEY GitHub secret is empty or missing.'
}

$outputDirectory = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

Write-Host 'Waiting 10 seconds before taking the screenshot...'
Start-Sleep -Seconds 10

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$screen = [System.Windows.Forms.Screen]::PrimaryScreen
if ($null -eq $screen) {
    throw 'No primary screen is available in the GitHub Actions runner session.'
}

$bounds = $screen.Bounds
$bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)

try {
    $graphics.CopyFromScreen(
        $bounds.Location,
        [System.Drawing.Point]::Empty,
        $bounds.Size
    )
    $bitmap.Save($OutputPath, [System.Drawing.Imaging.ImageFormat]::Jpeg)
}
finally {
    $graphics.Dispose()
    $bitmap.Dispose()
}

Write-Host "Screenshot saved to $OutputPath"

$imageBytes = [System.IO.File]::ReadAllBytes($OutputPath)
$requestBody = @{
    imageBase64 = [Convert]::ToBase64String($imageBytes)
} | ConvertTo-Json -Compress

$headers = @{
    Authorization = "Bearer $ApiKey"
}

Write-Host "Uploading screenshot to $WorkerUrl"
$response = Invoke-RestMethod `
    -Uri $WorkerUrl `
    -Method Post `
    -Headers $headers `
    -ContentType 'application/json' `
    -Body $requestBody

if (-not $response.success -or [string]::IsNullOrWhiteSpace($response.url)) {
    throw "Worker returned an unsuccessful response: $($response | ConvertTo-Json -Compress)"
}

Write-Host "Screenshot uploaded successfully: $($response.url)"

if ($env:GITHUB_OUTPUT) {
    "screenshot_url=$($response.url)" | Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}
