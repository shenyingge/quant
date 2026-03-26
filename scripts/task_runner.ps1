param(
    [ValidateSet("trading-service", "t0-daemon", "t0-sync-position")]
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
        $DisplayName = "Trading service"
        $MainArgs = @("main.py", "run")
    }
    "t0-daemon" {
        $LogPath = Join-Path $LogsDir "task_execution_t0_daemon.log"
        $DisplayName = "T0 daemon"
        $MainArgs = @("main.py", "t0-daemon")
    }
    "t0-sync-position" {
        $LogPath = Join-Path $LogsDir "task_execution_t0_sync.log"
        $DisplayName = "T0 position sync"
        $MainArgs = @("main.py", "t0-sync-position")
    }
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

    foreach ($line in Get-Content -Path $Path) {
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

function Invoke-LoggedProcess {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = $FilePath
    $startInfo.WorkingDirectory = $ProjectDir
    $startInfo.UseShellExecute = $false
    $startInfo.CreateNoWindow = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.Arguments = [string]::Join(" ", ($Arguments | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"{0}"' -f ($_.Replace('"', '\"'))
        } else {
            $_
        }
    }))

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    [void]$process.Start()

    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($stdout) {
        Append-LogContent $stdout.TrimEnd("`r", "`n")
    }

    if ($stderr) {
        Append-LogContent $stderr.TrimEnd("`r", "`n")
    }

    return $process.ExitCode
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

    $qmtProcess = Get-Process -Name "XtMiniQmt" -ErrorAction SilentlyContinue
    if (-not $qmtProcess) {
        throw "QMT client is not running"
    }
    Write-TaskLog "QMT client is running"

    $uvPath = Resolve-Uv
    if ($uvPath) {
        Write-TaskLog "Using uv at: $uvPath"
        Write-TaskLog "Syncing dependencies with uv"
        $syncExitCode = Invoke-LoggedProcess -FilePath $uvPath -Arguments @("sync")
        if ($syncExitCode -ne 0) {
            throw "uv sync failed with exit code $syncExitCode"
        }

        Write-TaskLog "Starting $DisplayName with uv"
        $exitCode = Invoke-LoggedProcess -FilePath $uvPath -Arguments (@("run", "python") + $MainArgs)
    } else {
        $pythonPath = Resolve-Python
        if (-not $pythonPath) {
            throw "Neither uv nor python was found"
        }

        Write-TaskLog "uv not found, falling back to python: $pythonPath"
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
