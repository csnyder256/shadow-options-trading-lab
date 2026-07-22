# register_mesh_tasks.ps1 - RUN ONCE to register the compute-mesh scheduled tasks (2026-07-09):
#   ATLAS-Premarket    05:15 CT (06:15 ET) -> build_day_briefing.py (crew fan-out + deterministic
#                      day flags -> runtime\day_briefing.json; degrades cleanly without API keys)
#   ATLAS-IVSnapshot   14:45 CT (15:45 ET) -> snapshot_iv.py --once (the EOD ATM-IV archive - 
#                      "the moat" - finally accumulates DAILY instead of on manual runs)
#   ATLAS-OvernightLab 15:25 CT (16:25 ET, after the local-model gate opens at 16:15 ET) ->
#                      run_overnight_lab.py (exit-grid paired replay + exit-efficiency + anomaly
#                      questions; LLM stages self-skip when gated/down)
#   ATLAS-CacheRefresh 15:35 CT (16:35 ET, post late-close window) -> refresh_intraday_cache.py
#                      (nightly 1-min IEX append for SPY/QQQ/IWM noise profiles - 
#                      opts-fix-noise-cache-refresh-v1; multi-day catch-up, weekend no-op)
#
#   powershell -ExecutionPolicy Bypass -File scripts\register_mesh_tasks.ps1
#
# All are safe no-ops on non-trading days (each script self-checks and exits 0/3; snapshot_iv
# gained its in-code non-session guard 2026-07-11 after the Saturday catch-up storm proved
# the claim false for it - build_day_briefing still fires-and-builds on weekends, which is
# why the cutover weekday-scoped these triggers).
# Times are LOCAL (Central). Pattern mirrors register_wake.ps1.
# CAUTION: re-running re-registers every task ENABLED and DAILY - it would UNDO the
# 2026-07-11 pivot_task_cutover.ps1 weekday scoping (Premarket/IVSnapshot/CacheRefresh/
# OvernightLab). After any re-run, re-run scripts\pivot_task_cutover.ps1 (elevated).
# REGISTERED OUTSIDE THIS SCRIPT (multi-trigger / non-python shapes; 2026-07-11 Wave 0):
#   ATLAS-CatalystArchive  08:30/12:30/17:30 daily -> archive_catalyst_events.py (opts-catalyst-archive-v1)
#   ATLAS-OptionsDay       weekdays 07:30 -> launch_options_day.ps1 (pivot_task_cutover.ps1;
#                          replaces the retired equity-era ATLAS-LiveDay, now Disabled)
#   ATLAS-Rehearsal        one-shot Sun 2026-07-12 18:00 -> launcher -SkipSessionCheck
#   ATLAS-ModelServer      at-logon + weekdays 15:22 -> start_llama_swap.ps1 (idempotent
#                          probe-first auto-start, owner-authorized 2026-07-11; START-only)

param(
    [string]$PremarketTime = "05:15",
    [string]$IVSnapshotTime = "14:45",
    [string]$LabTime = "15:25",
    [string]$CacheRefreshTime = "15:35"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { throw ".venv python not found at $py" }

function RegisterPyTask([string]$name, [string]$script, [string]$argline, [string]$at,
                        [int]$hours, [string]$desc) {
    $target = Join-Path $repo $script
    if (-not (Test-Path $target)) { Write-Host "SKIP ${name}: $script not found"; return }
    $action = New-ScheduledTaskAction -Execute $py `
        -Argument "`"$target`" $argline" -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Daily -At $at
    $settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours $hours) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings `
        -Description $desc -Force | Out-Null
    Write-Host "Registered '$name' daily at $at (local) -> $script"
}

RegisterPyTask "ATLAS-Premarket" "scripts\build_day_briefing.py" "" $PremarketTime 1 `
    "ATLAS compute mesh: premarket crew fan-out + deterministic day briefing (runtime\day_briefing.json)"
RegisterPyTask "ATLAS-IVSnapshot" "scripts\snapshot_iv.py" "--once" $IVSnapshotTime 1 `
    "ATLAS compute mesh: 15:45 ET EOD ATM-IV snapshot into runtime\options_iv.db (the IV-rank archive)"
RegisterPyTask "ATLAS-OvernightLab" "scripts\run_overnight_lab.py" "--once" $LabTime 8 `
    "ATLAS compute mesh: nightly options-shadow lab (exit-grid paired replay, exit efficiency, anomaly questions; gated LLM stages)"
RegisterPyTask "ATLAS-CacheRefresh" "scripts\refresh_intraday_cache.py" "" $CacheRefreshTime 1 `
    "ATLAS compute mesh: nightly intraday 1-min cache append SPY/QQQ/IWM (opts-fix-noise-cache-refresh-v1; multi-day catch-up; safe no-op on non-trading days)"

Write-Host "NOTE: PYTHONPATH is set by each script via sys.path bootstrap; working dir is the repo root."
Write-Host "Half-day caveat: ATLAS-IVSnapshot fires 14:45 CT year-round; on 13:00-close half days the"
Write-Host "snapshot lands post-close (registered known-limitation; snapshot_iv is time-agnostic)."