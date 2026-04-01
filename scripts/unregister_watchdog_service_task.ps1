$ErrorActionPreference = "Stop"

$taskName = "Quant_Watchdog_Service"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop

Write-Host "Removed scheduled task: $taskName"
