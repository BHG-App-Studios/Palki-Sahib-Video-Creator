[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$OperaExecutable,

    [Parameter(Mandatory = $true)]
    [uri]$Url
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not (Test-Path -LiteralPath $OperaExecutable -PathType Leaf)) {
    throw "Opera executable was not found: $OperaExecutable"
}

$registeredOpera = $null
foreach ($registryRoot in @('HKCU', 'HKLM')) {
    $registeredApplicationsPath = "${registryRoot}:\Software\RegisteredApplications"
    if (-not (Test-Path -LiteralPath $registeredApplicationsPath)) {
        continue
    }

    $properties = Get-ItemProperty -LiteralPath $registeredApplicationsPath
    foreach ($property in $properties.PSObject.Properties) {
        if (
            $property.Name -notmatch '^PS' -and
            $property.Name -match 'Opera' -and
            $property.Value
        ) {
            $registeredOpera = [pscustomobject]@{
                Name = $property.Name
                Root = $registryRoot
                CapabilitiesPath = [string]$property.Value
            }
            break
        }
    }

    if ($registeredOpera) {
        break
    }
}

if (-not $registeredOpera) {
    throw 'Opera was not found in Windows RegisteredApplications.'
}

$registryDrive = "$($registeredOpera.Root):\"
$urlAssociationsPath = Join-Path `
    -Path $registryDrive `
    -ChildPath "$($registeredOpera.CapabilitiesPath)\URLAssociations"
$urlAssociations = Get-ItemProperty -LiteralPath $urlAssociationsPath
$expectedHttpProgId = [string]$urlAssociations.http
$expectedHttpsProgId = [string]$urlAssociations.https

if (
    [string]::IsNullOrWhiteSpace($expectedHttpProgId) -or
    [string]::IsNullOrWhiteSpace($expectedHttpsProgId)
) {
    throw "Opera HTTP associations were not found at $urlAssociationsPath"
}

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$encodedRegisteredApp = [Uri]::EscapeDataString($registeredOpera.Name)
$settingsUri = "ms-settings:defaultapps?registeredAppUser=$encodedRegisteredApp"
Write-Host "Opening Windows Default Apps for $($registeredOpera.Name)"
Start-Process $settingsUri

$settingsProcess = $null
$processDeadline = (Get-Date).AddSeconds(30)
do {
    $settingsProcess = Get-Process -Name SystemSettings -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if (-not $settingsProcess) {
        Start-Sleep -Milliseconds 500
    }
} until ($settingsProcess -or (Get-Date) -ge $processDeadline)

if (-not $settingsProcess) {
    throw 'Windows Settings did not open.'
}

$root = [System.Windows.Automation.AutomationElement]::RootElement
$processCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty,
    $settingsProcess.Id
)
$buttonCondition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Button
)
$searchCondition = [System.Windows.Automation.AndCondition]::new(
    $processCondition,
    $buttonCondition
)

$setDefaultButton = $null
$observedButtonNames = @()
$buttonDeadline = (Get-Date).AddSeconds(30)
do {
    $buttons = $root.FindAll(
        [System.Windows.Automation.TreeScope]::Descendants,
        $searchCondition
    )

    foreach ($button in $buttons) {
        $buttonName = $button.Current.Name
        if ($buttonName) {
            $observedButtonNames += $buttonName
        }

        if (
            $buttonName -match '^(Set|Make) default$' -or
            $buttonName -match '^Make .+ your default browser$'
        ) {
            $setDefaultButton = $button
            break
        }
    }

    if (-not $setDefaultButton) {
        Start-Sleep -Milliseconds 500
    }
} until ($setDefaultButton -or (Get-Date) -ge $buttonDeadline)

if (-not $setDefaultButton) {
    $uniqueButtonNames = $observedButtonNames |
        Sort-Object -Unique |
        Select-Object -First 30
    throw "The default-browser button was not found. Observed buttons: $($uniqueButtonNames -join ', ')"
}

Write-Host "Clicking Windows Default Apps button: $($setDefaultButton.Current.Name)"
$invokePattern = $setDefaultButton.GetCurrentPattern(
    [System.Windows.Automation.InvokePattern]::Pattern
)
$invokePattern.Invoke()

$actualHttpProgId = $null
$actualHttpsProgId = $null
$associationDeadline = (Get-Date).AddSeconds(15)
do {
    Start-Sleep -Milliseconds 500
    $httpChoice = Get-ItemProperty `
        -LiteralPath 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice' `
        -ErrorAction SilentlyContinue
    $httpsChoice = Get-ItemProperty `
        -LiteralPath 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice' `
        -ErrorAction SilentlyContinue

    $actualHttpProgId = if ($httpChoice) {
        [string]$httpChoice.ProgId
    }
    else {
        $null
    }
    $actualHttpsProgId = if ($httpsChoice) {
        [string]$httpsChoice.ProgId
    }
    else {
        $null
    }
} until (
    (
        $actualHttpProgId -eq $expectedHttpProgId -and
        $actualHttpsProgId -eq $expectedHttpsProgId
    ) -or
    (Get-Date) -ge $associationDeadline
)

if (
    $actualHttpProgId -ne $expectedHttpProgId -or
    $actualHttpsProgId -ne $expectedHttpsProgId
) {
    throw @"
Windows did not confirm Opera as the default browser.
Expected HTTP/HTTPS: $expectedHttpProgId / $expectedHttpsProgId
Actual HTTP/HTTPS: $actualHttpProgId / $actualHttpsProgId
"@
}

Write-Host "Opera is the default HTTP/HTTPS browser: $actualHttpsProgId"

if ($settingsProcess.CloseMainWindow()) {
    $settingsProcess.WaitForExit(5000) | Out-Null
}

Write-Host "Opening $Url in Opera"
Start-Process `
    -FilePath $OperaExecutable `
    -ArgumentList @('--new-window', $Url.AbsoluteUri)

if ($env:GITHUB_OUTPUT) {
    "default_browser_progid=$actualHttpsProgId" |
        Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
    "opened_url=$($Url.AbsoluteUri)" |
        Out-File -FilePath $env:GITHUB_OUTPUT -Append -Encoding utf8
}
