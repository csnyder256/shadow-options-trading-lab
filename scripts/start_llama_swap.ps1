# start_llama_swap.ps1 - the owner's one-click model-server starter (2026-07-11).
#
# The equity launcher used to bring llama-swap up every morning; the all-in options pivot
# archived that launcher, leaving the server with NO starter (the options day deliberately
# needs no llama-swap - only the overnight lab, the headline taggers and the offload tooling
# do). This is the missing button. Double-click scripts\start_llama_swap.cmd to run it.
#
# What it does:
#   1. probes http://127.0.0.1:8080/v1/models - already up => says so, exits (always safe to click)
#   2. launches scripts\serve_models.ps1 minimized (the canonical runner:
#      C:\llama_swap\llama-swap.exe -config config\llama-swap.yaml -listen 127.0.0.1:8080,
#      timestamped logs under runtime\llama_swap_*.log)
#   3. polls the health endpoint up to 5 minutes (same budget the equity launcher used)
#   4. pre-warms glm-4.7-flash so the ~20GB VRAM load happens NOW, held open by the server's
#      healthCheckTimeout, instead of under the first real job's own request timeout
#
# It ONLY ever STARTS the server. It never stops, restarts, or reloads anything.
# After a REBOOT the server is gone until this is clicked again (models auto-idle via
# ttl 7200 while it runs; leaving it up costs nothing when idle).

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

function Probe {
    try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:8080/v1/models" | Out-Null; return $true }
    catch { return $false }
}

if (Probe) {
    Write-Host "llama-swap is ALREADY UP on http://127.0.0.1:8080 - nothing to do." -ForegroundColor Green
    exit 0
}

$swap = "C:\llama_swap\llama-swap.exe"
$cfg = Join-Path $repo "config\llama-swap.yaml"
if (-not (Test-Path $swap)) { Write-Host "llama-swap.exe MISSING at $swap" -ForegroundColor Red; exit 1 }
if (-not (Test-Path $cfg)) { Write-Host "config missing at $cfg" -ForegroundColor Red; exit 1 }

Write-Host "Starting llama-swap (minimized window; logs -> runtime\llama_swap_*.log)..."
Start-Process -WindowStyle Minimized powershell `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$repo\scripts\serve_models.ps1`""

$up = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep 5
    Write-Host -NoNewline "."
    if (Probe) { $up = $true; break }
}
Write-Host ""
if (-not $up) {
    Write-Host "SERVER NOT ANSWERING after ~5 min." -ForegroundColor Red
    Write-Host "Look at the NEWEST runtime\llama_swap_*.err.log for the reason, or check the minimized window."
    exit 2
}
Write-Host "SERVER UP on http://127.0.0.1:8080" -ForegroundColor Green

Write-Host "Pre-warming glm-4.7-flash (one-time ~1-3 min VRAM load; please wait)..."
try {
    $body = @{ model = "glm-4.7-flash"; max_tokens = 1
               messages = @(@{ role = "user"; content = "ok" }) } | ConvertTo-Json -Depth 4
    Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/v1/chat/completions" `
        -ContentType "application/json" -Body $body -TimeoutSec 300 | Out-Null
    Write-Host "GLM WARM - the server is fully ready." -ForegroundColor Green
} catch {
    Write-Host "Pre-warm did not finish ($($_.Exception.Message)) - NOT fatal; the first real request loads it instead." -ForegroundColor Yellow
}
exit 0
