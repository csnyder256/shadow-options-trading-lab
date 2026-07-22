# launch_live_day.ps1 - FORWARDING SHIM (2026-07-10 all-in options pivot).
#
# The equity launcher this name used to run is ARCHIVED at attic\scripts\launch_live_day.ps1
# (see attic\ARCHIVE_MANIFEST.md). The ATLAS-LiveDay scheduled task still points here and was
# registered ELEVATED (repointing it needs an admin shell - one-liner below), so this shim
# forwards to the options launcher. Equity-only flags (-Scanner, -BuildRsTable, -MaxTrades,
# -Flatten, -Telegram) are accepted and IGNORED.
#
# To retire this shim, run in an ELEVATED PowerShell:
#   $a = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\path\to\shadow-options-trading-lab\scripts\launch_options_day.ps1" -UntilTime 15:20'
#   Set-ScheduledTask -TaskName 'ATLAS-LiveDay' -Action $a

param(
    [int]$MaxTrades = 0,          # ignored (equity)
    [string]$UntilTime = "15:20",
    [switch]$Flatten,             # ignored (equity)
    [switch]$Scanner,             # ignored (equity)
    [switch]$BuildRsTable,        # ignored (equity)
    [switch]$Hub = $true,
    [switch]$NoBrowser,
    [switch]$Alerts = $true,
    [switch]$Telegram             # ignored (equity)
)

$here = $PSScriptRoot
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path (Join-Path (Split-Path -Parent $here) "runtime\launch.log") `
    -Value "[$ts] launch_live_day SHIM -> launch_options_day (equity flags ignored: Scanner=$Scanner BuildRsTable=$BuildRsTable Telegram=$Telegram)"

# dot-invoke in-process rather than powershell -File: -File cannot bind `-Switch:$false`
# tokens (they arrive as positional strings - a known 5.1 fragility the W1 refute flagged)
& (Join-Path $here "launch_options_day.ps1") -UntilTime $UntilTime -Hub:$Hub `
    -NoBrowser:$NoBrowser -Alerts:$Alerts
exit $LASTEXITCODE
