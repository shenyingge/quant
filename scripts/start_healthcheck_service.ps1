$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
Set-Location $repoRoot
$envFile = Join-Path $repoRoot ".env"

$pythonExe = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

function Get-DotEnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    if (-not (Test-Path $Path)) {
        return $null
    }

    foreach ($line in Get-Content -Path $Path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }

        $key, $value = $trimmed -split "=", 2
        if ($key.Trim() -eq $Name) {
            return $value.Trim().Trim("'`"")
        }
    }

    return $null
}

$healthcheckHost = if ($env:HEALTHCHECK_HOST) {
    $env:HEALTHCHECK_HOST
} else {
    Get-DotEnvValue -Path $envFile -Name "HEALTHCHECK_HOST"
}

if (-not $healthcheckHost) {
    $healthcheckHost = "127.0.0.1"
}

& $pythonExe "main.py" "health-server" "--host=$healthcheckHost"
