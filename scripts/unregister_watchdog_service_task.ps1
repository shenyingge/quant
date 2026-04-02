$ErrorActionPreference = "Stop"

$taskName = "Quant_Watchdog_Service"
$legacyCmsTaskNames = @("Quant_CMS_Service")

foreach ($name in @($taskName) + $legacyCmsTaskNames) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($null -ne $task) {
        Unregister-ScheduledTask -TaskName $name -Confirm:$false
        Write-Host "Removed scheduled task: $name"
    }
}
