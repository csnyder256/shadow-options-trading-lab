# register_strategy_lab_task.ps1 - registers ATLAS-StrategyLab (weekdays 07:35 CT).
# OWN registrar by design: scripts\register_mesh_tasks.ps1 re-runs re-enable EVERYTHING
# daily (documented footgun) - this script touches ONLY the lab task and is idempotent.
# Also registers ATLAS-VixRefresh (daily 15:40 CT) + ATLAS-EarningsRefresh (weekdays 05:20 CT),
# the two keyless/keyed wires the lab consumes (registered lab-strategy-runtime-v1).
#
#   powershell -ExecutionPolicy Bypass -File scripts\register_strategy_lab_task.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Py = Join-Path $Root ".venv\Scripts\python.exe"

function Register-LabTask([string]$Name, [string]$Action, [string]$TaskArgs, $Trigger) {
    $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "$Name already registered - replacing definition (state preserved as enabled)"
        Unregister-ScheduledTask -TaskName $Name -Confirm:$false
    }
    $act = New-ScheduledTaskAction -Execute $Action -Argument $TaskArgs -WorkingDirectory $Root
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 10)
    Register-ScheduledTask -TaskName $Name -Action $act -Trigger $Trigger -Settings $settings | Out-Null
    Write-Host "registered $Name"
}

# ATLAS-StrategyLab: weekdays 07:35 local (CT box) -> launcher (session-guarded inside)
$trigLab = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 07:35
Register-LabTask "ATLAS-StrategyLab" "powershell.exe" `
    "-NoProfile -ExecutionPolicy Bypass -File `"$Root\scripts\launch_strategy_lab.ps1`"" $trigLab

# ATLAS-VixRefresh: daily 15:40 local (after CBOE EOD files update; keyless)
$trigVix = New-ScheduledTaskTrigger -Daily -At 15:40
Register-LabTask "ATLAS-VixRefresh" $Py "`"$Root\scripts\refresh_vix_history.py`"" $trigVix

# ATLAS-EarningsRefresh: weekdays 05:20 local (premarket, before ATLAS-Premarket's 05:15? no -
# independent; earnings_week.json is read lazily whenever fresh)
$trigEarn = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 05:20
Register-LabTask "ATLAS-EarningsRefresh" $Py "`"$Root\scripts\refresh_earnings_calendar.py`"" $trigEarn

Write-Host "done - 3 tasks registered (StrategyLab wkdys 07:35, VixRefresh daily 15:40, EarningsRefresh wkdys 05:20)"
