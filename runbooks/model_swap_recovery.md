# Runbook: Model Swap / VRAM Recovery

The two models share one 24 GB GPU and hot-swap one-at-a-time via llama-swap. This covers the
new failure surface the dual-model design introduces.

## Symptoms
- Cycles log `skip=analyst_load_failed` (no analysis happened - safe) or
  `skip=auditor_load_failed_proposals_discarded` (analyst output discarded - safe, no trade).
- `swap_failure` / `vram_pressure` alerts.
- nvidia-smi shows VRAM not freeing between models over a long run (fragmentation).

## Quick checks
1. Is llama-swap up? `Invoke-WebRequest http://127.0.0.1:8080/v1/models` should return both model ids.
2. Free VRAM: `nvidia-smi --query-gpu=memory.free --format=csv,noheader`. A fresh load needs the
   model's footprint (GLM ~20 GB / Qwen ~18 GB) to fit after the other is evicted.
3. CUDA version: confirm the llama.cpp build is CUDA **12.x**, never 13.2 (gibberish on Qwen3.6).

## Recovery
1. **Restart the server** (defragments VRAM, clears a half-loaded model):
   `Stop-Process -Name llama-swap; Stop-Process -Name llama-server` then re-run
   `scripts/serve_models.ps1`.
2. The orchestrator fails safe: a failed analyst load skips the cycle; a failed auditor load
   discards the analyst proposal. **No trade is ever placed on a half-loaded GPU.** So a swap
   failure costs missed cycles, never an unsafe order - it is safe to let it retry while you fix
   serving.
3. If swaps keep failing after restart, drop the quant (GLM-4.7-Flash Q4_K_M / Qwen3.6-27B Q4_K_M)
   or the `--ctx-size`, or add the second GPU (both models stay resident, swap becomes a no-op).

## Endurance note
Restart llama-swap on a TTL / cycle-count cadence (e.g. daily) to pre-empt long-run VRAM
fragmentation on Windows. Exclude `C:\models` and `C:\llama_cpp` from Defender real-time scan.
