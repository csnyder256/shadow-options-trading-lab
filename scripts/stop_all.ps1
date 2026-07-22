# stop_all.ps1 - cleanly stop EVERY ATLAS process (e.g. for a weekend). Post-pivot (2026-07-10,
# all-in options; attic\ARCHIVE_MANIFEST.md): stops the options launcher(s), the shadow, the news
# tap, the alerter, the overnight lab, the monitoring hub, and llama-swap if it was started
# manually for the lab. The old-launcher/equity matches are kept for ONE transition week
# (2026-07-17) so a stale process from the pre-pivot world can still be cleaned up.
#
#   powershell -ExecutionPolicy Bypass -File scripts\stop_all.ps1
#
# IMPORTANT: if the day was launched from an ELEVATED PowerShell, its child processes are elevated
# too, and a normal shell gets "Access is denied" (and can't even read their command lines to match
# them). In that case RIGHT-CLICK PowerShell -> "Run as administrator" and run this again.

$ErrorActionPreference = "Continue"
$stopped = 0; $denied = 0

function StopMatch($desc, $procName, $cmdMatch) {
    Get-CimInstance Win32_Process -Filter "Name='$procName'" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($cmdMatch -and ($_.CommandLine -notlike "*$cmdMatch*")) { return }   # empty CommandLine = elevated/hidden -> skip (run elevated)
        try {
            Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
            Write-Host "  stopped $desc (PID $($_.ProcessId))"; $script:stopped++
        } catch {
            Write-Host "  DENIED  $desc (PID $($_.ProcessId)) -> needs an elevated shell"; $script:denied++
        }
    }
}

Write-Host "stopping ATLAS components..."
# STOP FLAG first: the launcher's crash-restart loop (2026-07-01) would otherwise resurrect the app
# up to 3x after we kill it. The launcher checks this flag each minute and shuts down cleanly.
$repo = Split-Path -Parent $PSScriptRoot
try { Set-Content -Path (Join-Path $repo "runtime\STOP_DAY.flag") -Value (Get-Date -Format s) -Encoding ascii } catch {}
StopMatch "options day launcher" "powershell.exe" "launch_options_day"
StopMatch "options shadow"     "python.exe"       "run_options_shadow"
StopMatch "news tap"           "python.exe"       "news_tap"
StopMatch "stall alerter"      "python.exe"       "alert_watch"
StopMatch "overnight lab"      "python.exe"       "run_overnight_lab"
StopMatch "monitoring hub"     "python.exe"       "watch_hub"
StopMatch "model server"       "llama-swap.exe"   $null
StopMatch "model worker"       "llama-server.exe" $null
# --- transition-week matches (equity world, archived 2026-07-10; remove after 2026-07-17) ---
StopMatch "OLD day launcher"   "powershell.exe"   "launch_live_day"
StopMatch "trader (atlas.app)" "python.exe"       "atlas.app"
StopMatch "guardian"           "python.exe"       "run_guardian"
StopMatch "control panel"      "python.exe"       "control_panel"
StopMatch "telegram bot"       "python.exe"       "telegram_bot"

Write-Host "done: $stopped stopped, $denied denied."
if ($denied -gt 0) { Write-Host "-> RE-RUN THIS IN AN ELEVATED PowerShell (Run as administrator) to stop the rest." }
$srv = $false; try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:8080/v1/models" | Out-Null; $srv = $true } catch {}
Write-Host ("model server still listening on :8080: {0}" -f $srv)
