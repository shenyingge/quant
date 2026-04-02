$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$taskName = "Quant_Watchdog_Service"
$legacyCmsTaskNames = @("Quant_CMS_Service")
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

$action = New-ScheduledTaskAction `
    -Execute $pythonExe `
    -Argument "main.py watchdog" `
    -WorkingDirectory $repoRoot

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Enforce single-entry deployment: the watchdog owns CMS server startup.
foreach ($legacyTaskName in $legacyCmsTaskNames) {
    $legacyTask = Get-ScheduledTask -TaskName $legacyTaskName -ErrorAction SilentlyContinue
    if ($null -ne $legacyTask) {
        Unregister-ScheduledTask -TaskName $legacyTaskName -Confirm:$false
        Write-Host "Removed legacy scheduled task: $legacyTaskName"
    }
}

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Force | Out-Null

Write-Host "Registered scheduled task: $taskName"
Write-Host "Single-entry mode enabled: watchdog is now the only startup task."
