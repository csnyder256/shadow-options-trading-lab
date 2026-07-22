# launch_options_day.ps1 - wake-to-run entry for an OPTIONS SHADOW day (ZERO live orders).
#
# ALL-IN OPTIONS pivot (2026-07-10; attic\ARCHIVE_MANIFEST.md): the equity stack (model server,
# preflight_live, atlas.app, Guardian, control panel, telegram bot) is ARCHIVED. This launcher
# runs ONLY: the options shadow trader (Tradier NBBO, no order path), the Benzinga news tap,
# the read-only monitoring hub, and the alerter in --options-only mode. It needs NO Robinhood,
# NO Alpaca and NO llama-swap at launch - the entire class of RH-auth-abort mornings is gone.
# A missing/bad Tradier token WARNS (page) and launches anyway: the shadow degrades to a
# heartbeat-only day by design, which is observable and recoverable, unlike an abort.
#
#   powershell -ExecutionPolicy Bypass -File scripts\launch_options_day.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\launch_options_day.ps1 -UntilTime 15:20

param(
    [string]$UntilTime = "15:20", # local (CT). 16:00 ET close + the late-close window (index-ETF
                                  # options quote to 16:15 ET; the 16:10 ET hard flat needs the
                                  # stack alive past 15:10 CT)
    [switch]$Hub = $true,         # read-only monitoring hub (http://127.0.0.1:8770/); default ON
    [switch]$NoBrowser,           # do not auto-open the hub in a browser
    [switch]$Alerts = $true,      # heartbeat alerter (ntfy/email), --options-only mode; default ON
    [switch]$SkipSessionCheck     # rehearsals only: boot the stack on a non-session day
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
$env:PYTHONPATH = $repo
Set-Location $repo
New-Item -ItemType Directory -Force (Join-Path $repo "runtime") | Out-Null

function Log($m) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] $m"
    Add-Content -Path (Join-Path $repo "runtime\launch.log") -Value "[$ts] $m"
}

# Pager: best-effort ntfy push; a page failure never blocks anything.
function Page([string]$title, [string]$msg, [string]$priority = "urgent") {
    try {
        $cfg = Get-Content (Join-Path $repo "config\alerts.json") -Raw | ConvertFrom-Json
        $topic = $cfg.ntfy.topic
        if ($topic) {
            Invoke-RestMethod -Method Post -Uri "https://ntfy.sh/$topic" -Body $msg `
                -Headers @{ Title = $title; Priority = $priority; Tags = "rotating_light" } `
                -TimeoutSec 10 | Out-Null
            Log "page pushed (ntfy): $title"
        }
    } catch { Log "page FAILED ($($_.Exception.Message)) - continuing" }
}

Log "=== launch_options_day: UntilTime=$UntilTime Hub=$Hub Alerts=$Alerts (options-only stack) ==="

# 0. Session + UntilTime guards (2026-07-11 Monday-readiness audit). The scheduled driver
# fires daily with StartWhenAvailable catch-up: a weekend/holiday wake used to boot the full
# stack onto Friday-frozen quotes (the runner ticks happily and writes a junk journal - seen
# live Sat 2026-07-11 12:58), and a post-close catch-up used to run OVERNIGHT via the old
# AddDays(1) fallback. Rehearsals pass -SkipSessionCheck. The session probe is FAIL-OPEN:
# a guard ERROR launches anyway (a lost session costs more than a junk weekend boot).
$end = [DateTime]::ParseExact($UntilTime, "HH:mm", $null)
if ((Get-Date) -gt $end) {
    Log "UntilTime $UntilTime already passed - clean exit (catch-up fire after close; no overnight run)"
    exit 0
}
if (-not $SkipSessionCheck) {
    & $py -c 'from datetime import date; from atlas.options.session_calendar import is_trading_day; raise SystemExit(0 if is_trading_day(date.today()) else 3)'
    if ($LASTEXITCODE -eq 3) {
        Log "not a trading session today - exiting (rehearsals: -SkipSessionCheck)"
        exit 0
    } elseif ($LASTEXITCODE -ne 0) {
        Log "WARN: session guard errored (exit $LASTEXITCODE) - launching anyway (fail-open)"
    }
}

# 1. Tiny Tradier preflight - WARN-and-launch, never abort (the shadow runs DEGRADED
# heartbeat-only without a token, which is observable; an abort is a silent lost day).
$pfScript = @"
import sys
from atlas.config_loader import FRAMEWORK_ROOT
from atlas.collect.tradier_data import TradierData
td = TradierData.from_local_config(FRAMEWORK_ROOT / 'config' / 'tradier_shadow.local.yaml') \
     or TradierData.from_local_config(FRAMEWORK_ROOT / 'config' / 'tradier.local.yaml')
if td is None:
    print('NO-TOKEN'); sys.exit(1)
try:
    q = td.get_quotes(['SPY'])
    print('OK' if q else 'EMPTY'); sys.exit(0 if q else 1)
except Exception as exc:
    print(f'FAIL {type(exc).__name__}: {exc}'); sys.exit(1)
"@
$pfFile = Join-Path $repo "runtime\options_preflight.py"
Set-Content -Path $pfFile -Value $pfScript -Encoding utf8
& $py $pfFile
if ($LASTEXITCODE -ne 0) {
    Log "TRADIER PREFLIGHT WARN (exit $LASTEXITCODE) - launching anyway (shadow degrades to heartbeat-only)"
    Page "ATLAS options: Tradier token WARN" ("Tradier quote preflight failed at $(Get-Date -Format HH:mm). " +
        "The shadow will run heartbeat-only (no fills recorded) until config\tradier_shadow.local.yaml is fixed. " +
        "The stack IS launching.") "high"
} else {
    Log "Tradier preflight GO"
}

# 2. Start the options shadow + news tap (session-scoped; stopped in finally).
$optProc = $null
$newsProc = $null
$flagProc = $null
$mentionProc = $null
$symProc = $null
$alertProc = $null

$optProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\run_options_shadow.py`"" `
    -RedirectStandardOutput (Join-Path $repo "runtime\options_shadow.out.log") `
    -RedirectStandardError  (Join-Path $repo "runtime\options_shadow.err.log")

try {
    Start-Sleep 3
    if (($optProc -eq $null) -or $optProc.HasExited) {
        Log "OPTIONS SHADOW FAILED TO START (code $($optProc.ExitCode)) - ABORT (nothing to run)"
        Page "ATLAS: OPTIONS DAY ABORTED" ("The options shadow failed to start at $(Get-Date -Format HH:mm) " +
            "(exit $($optProc.ExitCode)). See runtime\options_shadow.err.log. NOTHING is running today; " +
            "fix and rerun scripts\launch_options_day.ps1.")
        exit 3
    }
    Log "options shadow started (PID $($optProc.Id)) - paper contract identification live"

    # News tap: MULTI-SOURCE poller -> runtime\news_stream.jsonl (single writer); self-exits cleanly
    # without creds. Benzinga @10s (ops-news-tap-poll-10s-v1) + Finnhub (general/world) + GDELT
    # (geopolitical) on their own throttled cadence; per-source health -> runtime\news_sources_heartbeat.json.
    # Macro/world headlines carry symbols=[] and route to the observe-first macro sink, never orders.
    $newsProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\news_tap.py`" --sources benzinga,finnhub,gdelt --poll-seconds 10 --heartbeat `"$repo\runtime\news_tap_heartbeat.json`"" `
        -RedirectStandardOutput (Join-Path $repo "runtime\news_tap.out.log") `
        -RedirectStandardError  (Join-Path $repo "runtime\news_tap.err.log")
    Start-Sleep 1
    if ($newsProc.HasExited) { Log "news tap not running (code $($newsProc.ExitCode)) - likely no creds; see runtime\news_tap.out.log" }
    else { Log "news tap started (PID $($newsProc.Id)) - headline stream live" }

    # News-flag tap (opts-svc-news-flag-tap-v1): C6 classifier, first consumer of the stream.
    # Stage-0 enrichment (own jsonl; the shadow reads NOTHING from it yet); best-effort like
    # the news tap - a death costs flag evidence, never marks.
    $flagProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\news_flag_tap.py`"" `
        -RedirectStandardOutput (Join-Path $repo "runtime\news_flag_tap.out.log") `
        -RedirectStandardError  (Join-Path $repo "runtime\news_flag_tap.err.log")
    Start-Sleep 1
    if ($flagProc.HasExited) { Log "news-flag tap not running (code $($flagProc.ExitCode)); see runtime\news_flag_tap.err.log" }
    else { Log "news-flag tap started (PID $($flagProc.Id)) - headline classification live" }

    # Mention tap (opts-svc-mention-tap-v1): reddit + stocktwits attention collector. Its 5-day
    # acceleration baseline accrues ONLY while this runs - session-scoped here (was never
    # scheduled anywhere; found in the 2026-07-11 audit). Best-effort: a death costs mention
    # evidence, never marks. Zero consumers until the baseline matures.
    $mentionProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\mention_tap.py`"" `
        -RedirectStandardOutput (Join-Path $repo "runtime\mention_tap.out.log") `
        -RedirectStandardError  (Join-Path $repo "runtime\mention_tap.err.log")
    Start-Sleep 1
    if ($mentionProc.HasExited) { Log "mention tap not running (code $($mentionProc.ExitCode)); see runtime\mention_tap.err.log" }
    else { Log "mention tap started (PID $($mentionProc.Id)) - social mention counts live" }

    # Symbol-state poller (opts-svc-symbol-state-poller-v1): trading-halt RSS -> runtime\symbol_state.json,
    # the LIVE data source for the selector's halt DATA-VALIDITY gate (opts-ws3-halt-gate-v1). Best-
    # effort: a death just leaves the gate inert (fail-open, no file -> no state asserted). 45s cadence.
    $symProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\poll_symbol_state.py`" --poll-seconds 45" `
        -RedirectStandardOutput (Join-Path $repo "runtime\symbol_state.out.log") `
        -RedirectStandardError  (Join-Path $repo "runtime\symbol_state.err.log")
    Start-Sleep 1
    if ($symProc.HasExited) { Log "symbol-state poller not running (code $($symProc.ExitCode)); see runtime\symbol_state.err.log" }
    else { Log "symbol-state poller started (PID $($symProc.Id)) - halt data-quality gate live" }

    # Monitoring hub (read-only viewer; self-dedupes on :8770; left running after the day).
    if ($Hub) {
        $hubUp = $false
        try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:8770/healthz" | Out-Null; $hubUp = $true } catch {}
        if ($hubUp) {
            Log "monitoring hub already running on :8770 (reusing it)"
        } else {
            $hubProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\watch_hub.py`"" `
                -RedirectStandardOutput (Join-Path $repo "runtime\watch_hub.out.log") `
                -RedirectStandardError  (Join-Path $repo "runtime\watch_hub.err.log")
            for ($i = 0; $i -lt 10; $i++) {
                Start-Sleep 1
                try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:8770/healthz" | Out-Null; $hubUp = $true; break } catch {}
            }
            if ($hubUp) { Log "monitoring hub started on http://127.0.0.1:8770/ (PID $($hubProc.Id))" }
            else { Log "WARN: hub not healthy on :8770 within ~10s (non-critical; see runtime\watch_hub.err.log)" }
        }
        if ($hubUp -and -not $NoBrowser -and [Environment]::UserInteractive) {
            try { Start-Process "http://127.0.0.1:8770/" } catch { Log "WARN: could not open browser: $($_.Exception.Message)" }
        }
    }

    # Alerter in --options-only mode: heartbeat watches only (options shadow); the equity
    # analyst/:8080/halt/broker/app watches are OFF (no llama-swap or orchestrator exists to watch).
    if ($Alerts) {
        $alertProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\alert_watch.py`" --options-only" `
            -RedirectStandardOutput (Join-Path $repo "runtime\alert_watch.out.log") `
            -RedirectStandardError  (Join-Path $repo "runtime\alert_watch.err.log")
        Start-Sleep 1
        if ($alertProc.HasExited) { Log "WARN: alert_watch exited immediately (code $($alertProc.ExitCode)); see runtime\alert_watch.err.log" }
        else { Log "alerter started (PID $($alertProc.Id)) - options-only heartbeat watch" }
    }

    # 3. Run until the close. Component deaths never tear down survivors: the shadow gets up to
    # 3 respawns with fresh log files (the pid lock's dead-pid reclaim admits the respawn).
    # ($end computed + validated by guard 0 - a start after UntilTime never gets this far.)
    $stopFlag = Join-Path $repo "runtime\STOP_DAY.flag"
    try { if (Test-Path $stopFlag) { Remove-Item $stopFlag -Force } } catch {}
    $optRestarts = 0
    Log "running until $UntilTime (STOP_DAY.flag honored)"
    while ((Get-Date) -lt $end) {
        Start-Sleep 60
        if (Test-Path $stopFlag) {
            Log "STOP_DAY flag detected (stop_all.ps1) - ending the day now"
            break
        }
        if ($optProc -and $optProc.HasExited) {
            if ($optRestarts -lt 3) {
                $optRestarts++
                Log "options shadow exited early (code $($optProc.ExitCode)) - RESTARTING ($optRestarts/3); crash log preserved in options_shadow.err.log"
                $optProc = Start-Process -PassThru -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\run_options_shadow.py`"" `
                    -RedirectStandardOutput (Join-Path $repo "runtime\options_shadow.restart$optRestarts.out.log") `
                    -RedirectStandardError  (Join-Path $repo "runtime\options_shadow.restart$optRestarts.err.log")
            } else {
                Log "options shadow exited AGAIN (code $($optProc.ExitCode)) after 3 restarts - giving up for the day"
                Page "ATLAS: options shadow DOWN for the day" ("The shadow crashed 4x by $(Get-Date -Format HH:mm); " +
                    "giving up. Today's evidence stops here. See runtime\options_shadow.err.log / restart logs.")
                $optProc = $null
            }
            continue
        }
        if ($newsProc -and $newsProc.HasExited) { $newsProc = $null }   # news tap is best-effort; no respawn
    }
} finally {
    Log "stopping options shadow + news/mention taps + symbol-state poller + alerter (clean day-end teardown; hub left running)"
    foreach ($p in @($optProc, $newsProc, $flagProc, $mentionProc, $symProc, $alertProc)) { try { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force } } catch {} }
    Log "=== options day complete ==="
}
