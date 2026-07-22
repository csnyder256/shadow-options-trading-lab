# launch_strategy_lab.ps1 - supervisor for the STRATEGY LAB process only (mission 20260719,
# lab-strategy-runtime-v1). Clone of launch_options_day.ps1's skeleton: session guard,
# WARN-never-abort preflight, 3-respawn loop, STOP flag teardown, ntfy page on death.
#
# It deliberately does NOT start news taps / poll_symbol_state / watch_hub / alert_watch - 
# those are session-scoped children of the MAIN launcher; double-starting collides on
# single-writer files. The lab reads their outputs, it never owns them.
#
#   powershell -ExecutionPolicy Bypass -File scripts\launch_strategy_lab.ps1 [-UntilTime 15:20]
#       [-SkipSessionCheck]

param(
    [string]$UntilTime = "15:20",
    [switch]$SkipSessionCheck
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Runner = Join-Path $Root "scripts\run_strategy_lab.py"
$Runtime = Join-Path $Root "runtime"
$StopDay = Join-Path $Runtime "STOP_DAY.flag"
$StopLab = Join-Path $Runtime "STOP_LAB.flag"
$LogFile = Join-Path $Runtime "strategy_lab_launcher.log"

function Log([string]$msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    try { Add-Content -Path $LogFile -Value $line -Encoding utf8 } catch {}
}

function Page([string]$msg) {
    # best-effort ntfy page via the platform's alerts.json topic (same channel as the main stack)
    try {
        $alerts = Get-Content (Join-Path $Root "config\alerts.json") -Raw | ConvertFrom-Json
        $topic = $alerts.ntfy_topic
        if ($topic) {
            Invoke-RestMethod -Method Post -Uri "https://ntfy.sh/$topic" -Body $msg `
                -TimeoutSec 10 | Out-Null
        }
    } catch {}
}

# ---- session guard (weekend/holiday catch-up runs exit 0 silently) --------------------------
if (-not $SkipSessionCheck) {
    $probe = & $Py -c "import sys; sys.path.insert(0, r'$Root'); from datetime import date; from atlas.options.session_calendar import is_trading_day; sys.exit(0 if is_trading_day(date.today()) else 3)"
    if ($LASTEXITCODE -eq 3) { Log "not a trading day - exiting quietly"; exit 0 }
    if ($LASTEXITCODE -ne 0) { Log "session probe failed (exit $LASTEXITCODE) - WARN, launching anyway" }
}

if (Test-Path $StopDay) { Log "STOP_DAY.flag present - refusing to launch"; exit 0 }
if (Test-Path $StopLab) { Log "STOP_LAB.flag present - refusing to launch"; exit 0 }

# ---- preflight (WARN-never-abort: a degraded observable day beats a silent lost day) --------
if (-not (Test-Path (Join-Path $Root "config\tradier.local.yaml"))) {
    Log "WARN: config\tradier.local.yaml missing - lab will run heartbeat-only (degraded)"
}

# ---- respawn loop ---------------------------------------------------------------------------
$deadline = [datetime]::ParseExact($UntilTime, "HH:mm", $null)
$respawns = 0
while ($true) {
    if ((Get-Date).TimeOfDay -ge $deadline.TimeOfDay) { Log "UntilTime $UntilTime reached - done"; break }
    if ((Test-Path $StopDay) -or (Test-Path $StopLab)) { Log "stop flag - done"; break }
    Log "starting run_strategy_lab.py (respawn #$respawns)"
    & $Py $Runner --interval 10
    $code = $LASTEXITCODE
    if ((Test-Path $StopDay) -or (Test-Path $StopLab)) { Log "stop flag after exit $code - done"; break }
    if ((Get-Date).TimeOfDay -ge $deadline.TimeOfDay) { break }
    $respawns++
    if ($respawns -gt 3) {
        Log "lab died $respawns times (last exit $code) - paging and giving up for the day"
        Page "ATLAS strategy lab DOWN after 3 respawns (exit $code)"
        break
    }
    Log "lab exited $code - respawning in 30s"
    Start-Sleep -Seconds 30
}
Log "launcher done"
