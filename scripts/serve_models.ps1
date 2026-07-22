# serve_models.ps1 - launch the llama-swap proxy in front of both GGUFs (single-active).
# Ops/documentation only; the orchestrator never edits this. Run in its own terminal.
#
# Prereqs (one-time):
#   - NVIDIA driver present (nvidia-smi works); CUDA 12.x runtime (NOT 13.2).
#   - llama.cpp Windows CUDA build extracted to C:\llama_cpp\ (llama-server.exe + DLLs).
#   - llama-swap.exe in C:\llama_swap\.
#   - Models at C:\models\glm\ and C:\models\qwen\ (already downloaded).
#   - Recommended: exclude C:\models and C:\llama_cpp from Defender real-time scan.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$swap = "C:\llama_swap\llama-swap.exe"
$cfg  = Join-Path $repo "config\llama-swap.yaml"

if (-not (Test-Path $swap)) { throw "llama-swap not found at $swap" }
if (-not (Test-Path $cfg))  { throw "llama-swap config not found at $cfg" }

# Persist llama-swap's stdout/stderr to timestamped files under runtime/ so a mid-session model-server
# stall/crash (e.g. the 2026-06-25 end-of-day analyst TimeoutErrors) is DIAGNOSABLE after the fact -
# previously the server logged only to this console window and nothing survived on disk. Separate out/err
# files (Start-Process cannot point both streams at one file); timestamped per launch so a crash log is
# never overwritten by the next day's start. Do NOT use 2>&1 or *> on a native exe here - under PS5.1 that
# wraps stderr as NativeCommandErrors and trips ErrorActionPreference=Stop on the first stderr line.
$runtime = Join-Path $repo "runtime"
New-Item -ItemType Directory -Force $runtime | Out-Null
# bounded retention: drop llama-swap logs older than 14 days (only ever matches its own files).
Get-ChildItem $runtime -Filter "llama_swap_*.log" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-14) } |
    Remove-Item -Force -ErrorAction SilentlyContinue
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$swapOut = Join-Path $runtime "llama_swap_$stamp.out.log"
$swapErr = Join-Path $runtime "llama_swap_$stamp.err.log"
Write-Host "Launching llama-swap on http://127.0.0.1:8080 (single-active GLM-4.7-Flash / Qwen3.6-27B)"
Write-Host "  logs -> $swapOut"
Write-Host "         $swapErr"
$proc = Start-Process -PassThru -Wait -NoNewWindow $swap `
    -ArgumentList "-config","`"$cfg`"","-listen","127.0.0.1:8080" `
    -RedirectStandardOutput $swapOut -RedirectStandardError $swapErr
$exitStamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $swapErr -Value "[$exitStamp] llama-swap process EXITED with code $($proc.ExitCode)"
Write-Host "[$exitStamp] llama-swap exited (code $($proc.ExitCode))"
