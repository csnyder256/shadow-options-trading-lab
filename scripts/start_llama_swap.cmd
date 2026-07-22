@echo off
rem start_llama_swap.cmd - DOUBLE-CLICK ME to start the ATLAS model server (llama-swap).
rem Safe to click any time: if the server is already running it just says so and exits.
rem No admin needed. Details/logic: start_llama_swap.ps1 (same folder).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_llama_swap.ps1"
echo.
pause
