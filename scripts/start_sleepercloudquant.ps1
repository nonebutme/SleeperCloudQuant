[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8010,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$entryPoint = Join-Path $projectRoot "scripts\run_formal_web_demo.py"
$runtimeDirectory = Join-Path $projectRoot "var\runtime"
$pidFile = Join-Path $runtimeDirectory "web-$Port.pid"
$stdoutLog = Join-Path $runtimeDirectory "web-$Port.stdout.log"
$stderrLog = Join-Path $runtimeDirectory "web-$Port.stderr.log"
$webUrl = "http://127.0.0.1:$Port/"

function Get-ListenerProcessIds {
    $pattern = "^\s*TCP\s+127\.0\.0\.1:$Port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    return @(netstat -ano -p tcp | ForEach-Object {
        if ($_ -match $pattern) { [int]$Matches[1] }
    } | Sort-Object -Unique)
}

function Test-SleeperCloudQuantPage {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $webUrl -TimeoutSec 2
        $health = Invoke-RestMethod -Uri ($webUrl + "api/system/health") -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content.Contains("SleeperCloudQuant") -and
            $health.application -eq "SleeperCloudQuant" -and $health.entrypoint -eq "main-web" -and $health.status -eq "ready"
    }
    catch { return $false }
}

function Test-ExpectedProcesses([int[]]$ProcessIds) {
    if ($ProcessIds.Count -eq 0) { return $false }
    $processes = @($ProcessIds | ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId=$_" })
    return $processes.Count -eq $ProcessIds.Count -and
        @($processes | Where-Object { [string]$_.CommandLine -notmatch "run_formal_web_demo\.py" }).Count -eq 0
}

function Open-SleeperCloudQuantPage {
    if (-not $NoBrowser) { Start-Process $webUrl }
}

$existingProcessIds = @(Get-ListenerProcessIds)
if ($existingProcessIds.Count -gt 0) {
    if (-not (Test-SleeperCloudQuantPage) -or -not (Test-ExpectedProcesses $existingProcessIds)) {
        throw "Port $Port has an unverified or older service. If it is SleeperCloudQuant, use the stop shortcut and start again. Nothing new was started."
    }
    New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
    Set-Content -LiteralPath $pidFile -Value ($existingProcessIds -join ',') -Encoding ascii
    Write-Host "SleeperCloudQuant is already running at $webUrl (listener PID(s): $($existingProcessIds -join ', '))."
    if ($existingProcessIds.Count -gt 1) {
        Write-Warning "Multiple verified SleeperCloudQuant instances share port $Port. Use the stop shortcut once, then start again to return to one instance."
    }
    Open-SleeperCloudQuantPage
    exit 0
}

if (-not (Test-Path -LiteralPath $entryPoint -PathType Leaf)) { throw "Web entry point not found: $entryPoint" }
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $python = $venvPython
}
else {
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $pythonCommand) { throw "Python was not found. Create .venv or install Python before starting SleeperCloudQuant." }
    $python = $pythonCommand.Source
}

New-Item -ItemType Directory -Force -Path $runtimeDirectory | Out-Null
$env:SCQ_WEB_PORT = [string]$Port
$arguments = @("-X", "pycache_prefix=tmp\launcher-pycache", "scripts\run_formal_web_demo.py")
$serverProcess = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog -PassThru
Write-Host "Starting SleeperCloudQuant at $webUrl..."

for ($attempt = 0; $attempt -lt 60; $attempt++) {
    if (Test-SleeperCloudQuantPage) {
        $listenerProcessIds = @(Get-ListenerProcessIds)
        if (-not (Test-ExpectedProcesses $listenerProcessIds)) { throw "The new listener could not be verified." }
        Set-Content -LiteralPath $pidFile -Value ($listenerProcessIds -join ',') -Encoding ascii
        Write-Host "SleeperCloudQuant is ready: $webUrl (listener PID(s): $($listenerProcessIds -join ', '))"
        Open-SleeperCloudQuantPage
        exit 0
    }
    if ($serverProcess.HasExited -and @(Get-ListenerProcessIds).Count -eq 0) {
        $errorTail = if (Test-Path -LiteralPath $stderrLog) { (Get-Content -LiteralPath $stderrLog -Tail 20) -join [Environment]::NewLine } else { "No error log was produced." }
        throw "SleeperCloudQuant exited during startup.$([Environment]::NewLine)$errorTail"
    }
    Start-Sleep -Milliseconds 500
}

if (-not $serverProcess.HasExited) { Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue }
$listenerProcessIds = @(Get-ListenerProcessIds)
if ((Test-SleeperCloudQuantPage) -and (Test-ExpectedProcesses $listenerProcessIds)) {
    Stop-Process -Id $listenerProcessIds -Force -ErrorAction SilentlyContinue
}
throw "SleeperCloudQuant did not become ready within 30 seconds. Check $stderrLog"
