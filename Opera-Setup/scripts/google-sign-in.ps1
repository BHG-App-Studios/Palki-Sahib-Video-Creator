[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OperaExecutable,

    [Parameter(Mandatory = $true)]
    [string]$Email,

    [Parameter(Mandatory = $true)]
    [string]$Password,

    [Parameter(Mandatory = $true)]
    [uri]$FinalUrl,

    [Parameter(Mandatory = $true)]
    [string]$ScreenshotDirectory
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $OperaExecutable -PathType Leaf)) {
    throw "Opera executable was not found: $OperaExecutable"
}

if ([string]::IsNullOrWhiteSpace($Email)) {
    throw 'The GOOGLE_EMAIL GitHub Actions secret is missing or empty.'
}

if ([string]::IsNullOrWhiteSpace($Password)) {
    throw 'The GOOGLE_PASSWORD GitHub Actions secret is missing or empty.'
}

if ($Email.Contains("`r") -or $Email.Contains("`n")) {
    throw 'The GOOGLE_EMAIL secret contains an unsupported line break.'
}

if ($Password.Contains("`r") -or $Password.Contains("`n")) {
    throw 'The GOOGLE_PASSWORD secret contains an unsupported line break.'
}

New-Item -ItemType Directory -Path $ScreenshotDirectory -Force | Out-Null

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;

public static class ForegroundWindow
{
    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}
'@

function Save-Screenshot {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    if ($null -eq $screen) {
        throw 'No primary screen is available for the sign-in screenshot.'
    }

    $outputPath = Join-Path $ScreenshotDirectory $Name
    $bounds = $screen.Bounds
    $bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)

    try {
        $graphics.CopyFromScreen(
            $bounds.Location,
            [System.Drawing.Point]::Empty,
            $bounds.Size
        )
        $bitmap.Save(
            $outputPath,
            [System.Drawing.Imaging.ImageFormat]::Jpeg
        )
    }
    finally {
        $graphics.Dispose()
        $bitmap.Dispose()
    }

    Write-Host "Saved sign-in screenshot: $outputPath"
}

function Focus-OperaWindow {
    $deadline = (Get-Date).AddSeconds(20)
    $operaWindow = $null

    do {
        $operaWindow = Get-Process -Name opera -ErrorAction SilentlyContinue |
            Where-Object { $_.MainWindowHandle -ne [IntPtr]::Zero } |
            Sort-Object StartTime -Descending |
            Select-Object -First 1

        if (-not $operaWindow) {
            Start-Sleep -Milliseconds 500
        }
    } until ($operaWindow -or (Get-Date) -ge $deadline)

    if (-not $operaWindow) {
        throw 'An interactive Opera window was not found.'
    }

    [ForegroundWindow]::ShowWindowAsync($operaWindow.MainWindowHandle, 9) |
        Out-Null
    Start-Sleep -Milliseconds 300

    if (-not [ForegroundWindow]::SetForegroundWindow($operaWindow.MainWindowHandle)) {
        throw 'Windows did not allow the Opera window to receive keyboard focus.'
    }

    Start-Sleep -Milliseconds 500
}

function Send-LiteralText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    foreach ($character in $Text.ToCharArray()) {
        $sendKeysText = switch ([string]$character) {
            '+' { '{+}' }
            '^' { '{^}' }
            '%' { '{%}' }
            '~' { '{~}' }
            '(' { '{(}' }
            ')' { '{)}' }
            '[' { '{[}' }
            ']' { '{]}' }
            '{' { '{{}' }
            '}' { '{}}' }
            default { [string]$character }
        }

        [System.Windows.Forms.SendKeys]::SendWait($sendKeysText)
        Start-Sleep -Milliseconds 15
    }
}

Write-Host 'Waiting 10 seconds for the Google email page...'
Start-Sleep -Seconds 10
Focus-OperaWindow
Write-Host 'Entering the Google account email from the GitHub secret.'
Send-LiteralText -Text $Email
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Seconds 2
Save-Screenshot -Name '01-after-email-enter.jpg'

Write-Host 'Waiting 10 seconds for the Google password page...'
Start-Sleep -Seconds 10
Focus-OperaWindow
Write-Host 'Entering the Google account password from the GitHub secret.'
Send-LiteralText -Text $Password
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Seconds 2
Save-Screenshot -Name '02-after-password-enter.jpg'

Write-Host 'Waiting 10 seconds for the post-sign-in page...'
Start-Sleep -Seconds 10
Focus-OperaWindow
Write-Host 'Pressing Enter once on the post-sign-in page.'
[System.Windows.Forms.SendKeys]::SendWait('{ENTER}')
Start-Sleep -Seconds 2
Save-Screenshot -Name '03-after-google-enter.jpg'

Write-Host 'Waiting 10 seconds for Google sign-in to finish...'
Start-Sleep -Seconds 10
Save-Screenshot -Name '04-before-youtube-url.jpg'

Write-Host "Opening the final YouTube URL in Opera: $FinalUrl"
Start-Process `
    -FilePath $OperaExecutable `
    -ArgumentList @('--new-window', $FinalUrl.AbsoluteUri)
Start-Sleep -Seconds 10
Save-Screenshot -Name '05-after-youtube-url.jpg'

if ($env:GITHUB_OUTPUT) {
    "opened_url=$($FinalUrl.AbsoluteUri)" |
        Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}
