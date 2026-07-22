# pivot_task_cutover.ps1 - ONE-SHOT weekend cutover (2026-07-11, Monday-readiness audit).
# Retires the equity-era ATLAS-LiveDay daily driver and puts the OPTIONS day on its own
# properly-scoped schedule, with tomorrow evening's rehearsal as the first timed run.
#
#   RUN ELEVATED (Start menu -> type "powershell" -> right-click -> Run as Administrator):
#     powershell -ExecutionPolicy Bypass -File C:\path\to\shadow-options-trading-lab\scripts\pivot_task_cutover.ps1
#
# ATLAS-LiveDay was registered ELEVATED on 2026-06-24, so disabling/repointing it needs an
# admin shell - that is the only reason this script requires elevation.
#
# What it does (idempotent - safe to re-run):
#   1. If today's ATLAS-LiveDay instance is still running (the Sat 12:58 catch-up boot),
#      drops runtime\STOP_DAY.flag so the launcher tears itself down CLEANLY (<=~2.5 min),
#      then DISABLES ATLAS-LiveDay. The registration stays as a disabled tombstone;
#      delete it later with:  Unregister-ScheduledTask ATLAS-LiveDay
#   2. Registers ATLAS-Rehearsal: one-shot SUNDAY 2026-07-12 18:00 CT ->
#      launch_options_day.ps1 -SkipSessionCheck -UntilTime 18:45
#      (45-minute boot rehearsal: all five services + mention tap start, hub opens in the
#      browser, clean teardown at 18:45, hub stays up. 18:00 is outside session minutes so
#      the alerter's tick-staleness gate is naturally quiet.)
#   3. Registers ATLAS-OptionsDay: WEEKDAYS 07:30 CT -> launch_options_day.ps1
#      -UntilTime 15:20 (direct - no launch_live_day shim). Holidays self-skip via the
#      launcher's new session guard; a missed fire catches up on wake (StartWhenAvailable)
#      and a post-close catch-up now exits cleanly instead of running overnight.
#   4. Enables ATLAS-OvernightLab, first fire MONDAY 2026-07-13 15:25 CT, weekdays
#      thereafter - the "Sunday rehearsal re-enables the lab" step done here so no weekend
#      fire is possible. Its LLM stages still self-gate on llama-swap health + localgate.
#   5. Weekday-scopes the collectors that should not fire on weekends (times unchanged):
#      ATLAS-Premarket 05:15 (burns cloud-crew quota on a Saturday for a briefing Monday
#      overwrites), ATLAS-IVSnapshot 14:45 (Friday-stale chains; now ALSO guarded in-code),
#      ATLAS-CacheRefresh 15:35 (weekend fires were already no-ops; this just stops the
#      pointless spawns).
#   NOT touched: ATLAS-CatalystArchive (daily is correct - TTL rescue), ATLAS-AuthKeepalive
#   (Sun 18:00 grading-token refresh; runs alongside the rehearsal without conflict),
#   ATLAS-AutoEOD (weekdays 17:00, first fire Monday - supervised).

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repo "scripts\launch_options_day.ps1"
if (-not (Test-Path $launcher)) { throw "launcher not found: $launcher" }
$weekdays = @('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')

function LauncherAction([string]$extraArgs) {
    New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$launcher`" $extraArgs" `
        -WorkingDirectory $repo
}

# ---- 1. stop + disable ATLAS-LiveDay ------------------------------------------------------
$ld = Get-ScheduledTask -TaskName 'ATLAS-LiveDay' -ErrorAction SilentlyContinue
if ($null -eq $ld) {
    Write-Host "[1/5] ATLAS-LiveDay: not found (already removed) - nothing to disable"
} else {
    if ($ld.State -eq 'Running') {
        Write-Host "[1/5] ATLAS-LiveDay is RUNNING - dropping STOP_DAY.flag for the launcher's own clean teardown..."
        $flag = Join-Path $repo "runtime\STOP_DAY.flag"
        New-Item -ItemType File -Path $flag -Force | Out-Null
        $deadline = (Get-Date).AddSeconds(150)   # launcher polls the flag every 60s
        while ((Get-Date) -lt $deadline) {
            Start-Sleep -Seconds 10
            if ((Get-ScheduledTask -TaskName 'ATLAS-LiveDay').State -ne 'Running') { break }
        }
        try { Remove-Item $flag -Force -ErrorAction Stop } catch {}
        if ((Get-ScheduledTask -TaskName 'ATLAS-LiveDay').State -eq 'Running') {
            Write-Host "      still running after 150s - hard-stopping the task"
            Write-Host "      (hard stop orphans the service pythons: check Task Manager for leftover python.exe)"
            Stop-ScheduledTask -TaskName 'ATLAS-LiveDay'
        } else {
            Write-Host "      clean teardown confirmed (services down, hub left running by design)"
        }
    }
    Disable-ScheduledTask -TaskName 'ATLAS-LiveDay' | Out-Null
    Write-Host "[1/5] ATLAS-LiveDay DISABLED (tombstone kept)"
}

# ---- 2. one-shot Sunday rehearsal ---------------------------------------------------------
$rehSettings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'ATLAS-Rehearsal' `
    -Action (LauncherAction "-SkipSessionCheck -UntilTime 18:45") `
    -Trigger (New-ScheduledTaskTrigger -Once -At ([datetime]"2026-07-12 18:00")) `
    -Settings $rehSettings `
    -Description "ATLAS one-shot: Sunday 2026-07-12 18:00 boot rehearsal of the options-day stack (45 min, then clean teardown; hub stays up)" `
    -Force | Out-Null
Write-Host "[2/5] ATLAS-Rehearsal registered: Sunday 2026-07-12 18:00 -> 18:45 (one-shot)"

# ---- 3. the weekday options-day driver ----------------------------------------------------
$daySettings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 10) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'ATLAS-OptionsDay' `
    -Action (LauncherAction "-UntilTime 15:20") `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At ([datetime]"2026-07-13 07:30")) `
    -Settings $daySettings `
    -Description "ATLAS options shadow day driver (weekdays 07:30 CT; replaces equity-era ATLAS-LiveDay; holidays self-skip via the launcher session guard)" `
    -Force | Out-Null
Write-Host "[3/5] ATLAS-OptionsDay registered: weekdays 07:30 CT (first fire Monday 2026-07-13)"

# ---- 4. enable the overnight lab, first fire Monday post-close ----------------------------
$lab = Get-ScheduledTask -TaskName 'ATLAS-OvernightLab' -ErrorAction SilentlyContinue
if ($null -eq $lab) {
    Write-Host "[4/5] ATLAS-OvernightLab: NOT FOUND - run scripts\register_mesh_tasks.ps1 first, then re-run this"
} else {
    Set-ScheduledTask -TaskName 'ATLAS-OvernightLab' `
        -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At ([datetime]"2026-07-13 15:25")) | Out-Null
    Enable-ScheduledTask -TaskName 'ATLAS-OvernightLab' | Out-Null
    Write-Host "[4/5] ATLAS-OvernightLab ENABLED: weekdays 15:25 CT, first fire Monday 2026-07-13"
}

# ---- 5. weekday-scope the daily collectors ------------------------------------------------
$scope = @(
    @{ Name = 'ATLAS-Premarket';    At = [datetime]"2026-07-13 05:15" },
    @{ Name = 'ATLAS-IVSnapshot';   At = [datetime]"2026-07-13 14:45" },
    @{ Name = 'ATLAS-CacheRefresh'; At = [datetime]"2026-07-13 15:35" }
)
foreach ($s in $scope) {
    $t = Get-ScheduledTask -TaskName $s.Name -ErrorAction SilentlyContinue
    if ($null -eq $t) { Write-Host "[5/5] $($s.Name): not found - skipped"; continue }
    Set-ScheduledTask -TaskName $s.Name `
        -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $weekdays -At $s.At) | Out-Null
    Write-Host "[5/5] $($s.Name): weekday-scoped (time unchanged)"
}

# ---- final state --------------------------------------------------------------------------
Write-Host ""
Write-Host "=== resulting ATLAS task table ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like 'ATLAS-*' } | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    [pscustomobject]@{ Name = $_.TaskName; State = $_.State; NextRun = $i.NextRunTime }
} | Sort-Object Name | Format-Table -AutoSize
Write-Host "Cutover complete. Next timed run: ATLAS-Rehearsal, Sunday 18:00 CT."
