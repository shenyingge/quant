param(
    [ValidateSet("trading-service", "t0-daemon", "t0-sync-position", "minute-history-daily")]
    [string]$Mode = "trading-service"
)

$ErrorActionPreference = "Stop"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    # uv may print normal progress to stderr; rely on $LASTEXITCODE instead of stderr presence.
    $PSNativeCommandUseErrorActionPreference = $false
}
$ProjectDir = Split-Path -Parent $PSScriptRoot
$LogsDir = Join-Path $ProjectDir "logs"
$EnvFile = Join-Path $ProjectDir ".env"

if (-not (Test-Path $LogsDir)) {
    New-Item -ItemType Directory -Path $LogsDir | Out-Null
}

switch ($Mode) {
    "trading-service" {
        $LogPath = Join-Path $LogsDir "task_execution_trading.log"
        $DisplayName = "Trading engine"
        $MainArgs = @("main.py", "run")
    }
    "t0-daemon" {
        $LogPath = Join-Path $LogsDir "task_execution_t0_daemon.log"
        $DisplayName = "Strategy engine"
        $MainArgs = @("main.py", "t0-daemon")
    }
    "t0-sync-position" {
        $LogPath = Join-Path $LogsDir "task_execution_t0_sync.log"
        $DisplayName = "T0 position sync"
        $MainArgs = @("main.py", "t0-sync-position")
    }
    "minute-history-daily" {
        $LogPath = Join-Path $LogsDir "task_execution_minute_history.log"
        $DisplayName = "每日分钟行情导出"
        $MainArgs = @("main.py", "export-minute-daily")
    }
}

if ($Mode -eq "minute-history-daily") {
    $DisplayName = "每日分钟行情导出"
}

function Write-TaskLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Append-LogContent "[$timestamp] $Message"
}

function Append-LogContent {
    param([string]$Content)

    $fileStream = [System.IO.File]::Open($LogPath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
    try {
        $writer = New-Object System.IO.StreamWriter($fileStream, [System.Text.UTF8Encoding]::new($false))
        try {
            $writer.WriteLine($Content)
        }
        finally {
            $writer.Dispose()
        }
    }
    finally {
        $fileStream.Dispose()
    }
}

function Send-FeishuTaskNotification {
    param(
        [string]$Title,
        [string]$Message,
        [string]$Template = "red"
    )

    if (-not $env:FEISHU_WEBHOOK_URL) {
        return
    }

    try {
        $payload = @{
            msg_type = "interactive"
            card = @{
                header = @{
                    title = @{
                        content = $Title
                        tag = "plain_text"
                    }
                    template = $Template
                }
                elements = @(
                    @{
                        tag = "div"
                        text = @{
                            content = $Message
                            tag = "lark_md"
                        }
                    },
                    @{ tag = "hr" },
                    @{
                        tag = "div"
                        text = @{
                            content = "Time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
                            tag = "lark_md"
                        }
                    }
                )
            }
        }

        Invoke-RestMethod -Uri $env:FEISHU_WEBHOOK_URL -Method Post -ContentType "application/json" -Body ($payload | ConvertTo-Json -Depth 6) | Out-Null
    }
    catch {
        Write-TaskLog "Failed to send Feishu task notification: $($_.Exception.Message)"
    }
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw ".env file not found at $Path"
    }

    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $name, $value = $trimmed -split "=", 2
        $name = $name.Trim()
        $value = $value.Trim().Trim("'`"")

        if ($name) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Resolve-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $candidates = @(
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE "AppData\Roaming\Python\Scripts\uv.exe")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Resolve-Python {
    $venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }

    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Get-EnvIntSetting {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [int]$DefaultValue
    )

    $rawValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($rawValue)) {
        return $DefaultValue
    }

    $parsedValue = 0
    if ([int]::TryParse($rawValue, [ref]$parsedValue)) {
        return $parsedValue
    }

    Write-TaskLog "Invalid integer for ${Name}: $rawValue, using default $DefaultValue"
    return $DefaultValue
}

function Get-EnvBoolSetting {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [bool]$DefaultValue
    )

    $rawValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($rawValue)) {
        return $DefaultValue
    }

    switch ($rawValue.Trim().ToLowerInvariant()) {
        "1" { return $true }
        "true" { return $true }
        "yes" { return $true }
        "on" { return $true }
        "0" { return $false }
        "false" { return $false }
        "no" { return $false }
        "off" { return $false }
        default {
            Write-TaskLog "Invalid boolean for ${Name}: $rawValue, using default $DefaultValue"
            return $DefaultValue
        }
    }
}

function Invoke-LoggedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @(),

        [int]$TimeoutSeconds = 0
    )

    $stdoutPath = [System.IO.Path]::GetTempFileName()
    $stderrPath = [System.IO.Path]::GetTempFileName()

    try {
        $process = Start-Process `
            -FilePath $FilePath `
            -ArgumentList $Arguments `
            -WorkingDirectory $ProjectDir `
            -NoNewWindow `
            -PassThru `
            -RedirectStandardOutput $stdoutPath `
            -RedirectStandardError $stderrPath

        if ($TimeoutSeconds -gt 0) {
            if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
                try {
                    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
                }
                catch {
                }
                throw "Process timed out after $TimeoutSeconds seconds: $FilePath $($Arguments -join ' ')"
            }
        } else {
            $process.WaitForExit()
        }

        $stdout = Get-Content -Path $stdoutPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        $stderr = Get-Content -Path $stderrPath -Raw -Encoding UTF8 -ErrorAction SilentlyContinue

        if ($stdout) {
            Append-LogContent $stdout.TrimEnd("`r", "`n")
        }

        if ($stderr) {
            Append-LogContent $stderr.TrimEnd("`r", "`n")
        }

        return $process.ExitCode
    }
    finally {
        Remove-Item -LiteralPath $stdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrPath -Force -ErrorAction SilentlyContinue
    }
}

function Wait-ForQmtReady {
    param()

    $timeoutSeconds = Get-EnvIntSetting -Name "QMT_READY_TIMEOUT_SECONDS" -DefaultValue 900
    $retryIntervalSeconds = Get-EnvIntSetting -Name "QMT_READY_RETRY_INTERVAL_SECONDS" -DefaultValue 15
    $minimumAgeSeconds = Get-EnvIntSetting -Name "QMT_READY_PROCESS_AGE_SECONDS" -DefaultValue 20
    $stableChecksRequired = Get-EnvIntSetting -Name "QMT_READY_STABLE_CHECKS" -DefaultValue 2
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    $lastPid = $null
    $stableChecks = 0

    Write-TaskLog "Waiting for QMT readiness (timeout=${timeoutSeconds}s, interval=${retryIntervalSeconds}s, minimum_age=${minimumAgeSeconds}s, stable_checks=${stableChecksRequired})"

    while ((Get-Date) -lt $deadline) {
        $qmtProcess = Get-Process -Name "XtMiniQmt" -ErrorAction SilentlyContinue | Sort-Object StartTime | Select-Object -First 1
        if (-not $qmtProcess) {
            $lastPid = $null
            $stableChecks = 0
            Write-TaskLog "QMT process not found yet, retrying..."
        } else {
            if ($qmtProcess.Id -eq $lastPid) {
                $stableChecks += 1
            } else {
                $lastPid = $qmtProcess.Id
                $stableChecks = 1
            }

            $processAgeSeconds = [int]((Get-Date) - $qmtProcess.StartTime).TotalSeconds
            $isResponding = $true
            try {
                if ($null -ne $qmtProcess.Responding) {
                    $isResponding = [bool]$qmtProcess.Responding
                }
            }
            catch {
                $isResponding = $true
            }

            if (-not $isResponding) {
                Write-TaskLog "QMT process is not responding yet (pid=$($qmtProcess.Id)), retrying..."
            } elseif ($processAgeSeconds -lt $minimumAgeSeconds) {
                Write-TaskLog "QMT process is too new (pid=$($qmtProcess.Id), age=${processAgeSeconds}s), retrying..."
            } elseif ($stableChecks -lt $stableChecksRequired) {
                Write-TaskLog "QMT process has not been stable long enough (pid=$($qmtProcess.Id), stable_checks=${stableChecks}/${stableChecksRequired}), retrying..."
            } else {
                Write-TaskLog "QMT process is ready (pid=$($qmtProcess.Id), age=${processAgeSeconds}s, stable_checks=${stableChecks})"
                return
            }
        }

        Start-Sleep -Seconds $retryIntervalSeconds
    }

    throw "QMT client did not become ready within $timeoutSeconds seconds"
}

Set-Location $ProjectDir
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

try {
    Write-TaskLog "========================================="
    Write-TaskLog "Task started for mode: $Mode"
    Write-TaskLog "Project directory: $ProjectDir"

    Import-DotEnv -Path $EnvFile
    Write-TaskLog "Loaded environment variables from .env"

    $pythonPath = Resolve-Python
    if (-not $pythonPath) {
        throw "Python was not found for task startup"
    }
    Write-TaskLog "Using python for task startup: $pythonPath"
    Wait-ForQmtReady

    $preferUv = Get-EnvBoolSetting -Name "TASK_RUNNER_USE_UV" -DefaultValue $false
    $syncOnStart = Get-EnvBoolSetting -Name "TASK_RUNNER_SYNC_ON_START" -DefaultValue $false
    $uvPath = Resolve-Uv
    if ($preferUv -and $uvPath) {
        Write-TaskLog "Using uv at: $uvPath"
        if ($syncOnStart) {
            Write-TaskLog "Syncing dependencies with uv"
            $syncExitCode = Invoke-LoggedProcess -FilePath $uvPath -Arguments @("sync")
            if ($syncExitCode -ne 0) {
                throw "uv sync failed with exit code $syncExitCode"
            }
        } else {
            Write-TaskLog "Skipping uv sync on startup"
        }

        Write-TaskLog "Starting $DisplayName with uv"
        $exitCode = Invoke-LoggedProcess -FilePath $uvPath -Arguments (@("run", "python") + $MainArgs)
    } else {
        if ($preferUv -and -not $uvPath) {
            Write-TaskLog "uv was requested but not found, falling back to python: $pythonPath"
        } else {
            Write-TaskLog "Using python directly: $pythonPath"
        }
        Write-TaskLog "Starting $DisplayName with python"
        $exitCode = Invoke-LoggedProcess -FilePath $pythonPath -Arguments $MainArgs
    }

    Write-TaskLog "$DisplayName exited with code: $exitCode"
    if ($exitCode -ne 0) {
        Send-FeishuTaskNotification `
            -Title "Task exited unexpectedly" `
            -Message "Task: $DisplayName`nMode: $Mode`nExit code: $exitCode`nLog: $LogPath" `
            -Template "red"
    }
    exit $exitCode
}
catch {
    Write-TaskLog "ERROR: $($_.Exception.Message)"
    Send-FeishuTaskNotification `
        -Title "Task startup failed" `
        -Message "Task: $DisplayName`nMode: $Mode`nError: $($_.Exception.Message)`nLog: $LogPath" `
        -Template "red"
    throw
}
finally {
    Write-TaskLog "Task ended for mode: $Mode"
    Write-TaskLog "========================================="
}
