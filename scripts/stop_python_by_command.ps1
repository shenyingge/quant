param(
    [Parameter(Mandatory = $true)]
    [string]$Pattern,

    [string]$LogFile
)

$ErrorActionPreference = "Stop"

function Write-StopLog {
    param([string]$Message)
    if (-not $LogFile) {
        return
    }

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $LogFile -Value "[$timestamp] $Message"
}

if ($LogFile) {
    $logDir = Split-Path -Parent $LogFile
    if ($logDir -and -not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }
}

$processes = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -ieq "python.exe" -or $_.Name -ieq "pythonw.exe") -and
    $_.CommandLine -and
    $_.CommandLine -like "*$Pattern*"
}

if (-not $processes) {
    Write-StopLog "No python process matched pattern: $Pattern"
    exit 0
}

foreach ($process in $processes) {
    Write-StopLog "Stopping PID $($process.ProcessId): $($process.CommandLine)"
    Stop-Process -Id $process.ProcessId -Force
}

Write-StopLog "Stopped $($processes.Count) process(es) for pattern: $Pattern"
