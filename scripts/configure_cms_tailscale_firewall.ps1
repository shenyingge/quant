$ErrorActionPreference = "Stop"

$ruleName = "Quant CMS Server Tailscale Only"
$port = if ($env:CMS_SERVER_PORT) { $env:CMS_SERVER_PORT } else { "8780" }

$existingRules = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existingRules) {
    $existingRules | Remove-NetFirewallRule
}

New-NetFirewallRule `
    -DisplayName $ruleName `
    -Direction Inbound `
    -Action Allow `
    -Enabled True `
    -Profile Any `
    -Protocol TCP `
    -LocalPort $port `
    -RemoteAddress "100.64.0.0/10" | Out-Null

Write-Host "Configured Windows Firewall rule '$ruleName' for TCP port $port from 100.64.0.0/10 only."
