[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8010,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot "var\runtime"
$pidFile = Join-Path $runtimeDirectory "web-$Port.pid"
$webUrl = "http://127.0.0.1:$Port/"
$pattern = "^\s*TCP\s+127\.0\.0\.1:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"

function Get-ListenerProcessIds {
    return @(netstat -ano -p tcp | ForEach-Object {
        if ($_ -match $pattern) { [int]$Matches[1] }
    } | Sort-Object -Unique)
}

$processIds = @(Get-ListenerProcessIds)
if ($processIds.Count -eq 0) {
    Write-Host "SleeperCloudQuant is not listening on port $Port."
    exit 0
}

$processes = @($processIds | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$_" })
$isExpectedCommand = $processes.Count -eq $processIds.Count -and
    @($processes | Where-Object { [string]$_.CommandLine -notmatch "run_formal_web_demo\.py" }).Count -eq 0
$isExpectedPage = $false
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $webUrl -TimeoutSec 2
    $isExpectedPage = $response.StatusCode -eq 200 -and $response.Content.Contains("SleeperCloudQuant")
}
catch { $isExpectedPage = $false }

if (-not ($isExpectedCommand -and $isExpectedPage)) {
    throw "Port $Port includes an unverified listener process. Nothing was stopped."
}
if ($CheckOnly) {
    Write-Host "Verified SleeperCloudQuant at $webUrl (listener PID(s): $($processIds -join ', ')). Check-only mode: nothing was stopped."
    exit 0
}

Stop-Process -Id $processIds
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (@(Get-ListenerProcessIds).Count -eq 0) { break }
    Start-Sleep -Milliseconds 250
}
if (@(Get-ListenerProcessIds).Count -gt 0) { throw "Listener processes did not release port $Port." }
if (Test-Path -LiteralPath $pidFile) { Remove-Item -LiteralPath $pidFile -Force }
Write-Host "SleeperCloudQuant stopped (listener PID(s): $($processIds -join ', '))."