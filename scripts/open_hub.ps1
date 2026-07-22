# open_hub.ps1 - ensure the read-only ATLAS monitoring hub is running, then open it in the browser.
#
#   powershell -ExecutionPolicy Bypass -File scripts\open_hub.ps1
#
# Safe to run ANYTIME: it never touches the trader (the hub is a separate read-only viewer - no atlas
# import, no GPU, no Robinhood calls). Use it to pull up the dashboard when a launch ran unattended (the
# wake task starts the hub, but if you were not at the desk the browser auto-open may have been skipped),
# or just to reopen the page. If the hub is already up it only opens the tab; otherwise it starts it first.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = Join-Path $repo ".venv\Scripts\python.exe"
$url = "http://127.0.0.1:8770/"

function HubUp {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "${url}healthz" | Out-Null; return $true }
    catch { return $false }
}

if (HubUp) {
    Write-Host "monitoring hub already running."
} else {
    if (-not (Test-Path $py)) { throw "venv python not found at $py" }
    Write-Host "starting monitoring hub (scripts\watch_hub.py) ..."
    New-Item -ItemType Directory -Force (Join-Path $repo "runtime") | Out-Null
    Start-Process -WindowStyle Hidden $py -ArgumentList "`"$repo\scripts\watch_hub.py`"" `
        -RedirectStandardOutput (Join-Path $repo "runtime\watch_hub.out.log") `
        -RedirectStandardError  (Join-Path $repo "runtime\watch_hub.err.log") | Out-Null
    for ($i = 0; $i -lt 12; $i++) { Start-Sleep 1; if (HubUp) { break } }
}

if (HubUp) { Write-Host "hub up -> opening $url"; Start-Process $url }
else { Write-Host "ERROR: hub did not come up on :8770 (see runtime\watch_hub.err.log)"; exit 1 }
