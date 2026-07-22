@echo off
REM opts-auto-claude-v1 (2026-07-11) - J1: nightly autonomous /eodreport on the owner's Claude plan.
REM REPORT-AND-PROPOSE mode: the deny-rules in .claude\autonomous-settings.json make the
REM decision core / runner / launchers / configs / schemas UNEDITABLE; fixes outside that
REM scope must land as sweep-ledger rows with status "proposed" + the morning summary.
REM Every run ends with a git commit on main tagged "autonomous:" - the reviewable diff IS
REM the audit trail (local repo, no remote; git push is deny-ruled anyway).
REM Scheduled as ATLAS-AutoEOD, weekdays 17:00 CT (after IVSnapshot 14:45 / CacheRefresh 15:35
REM / OvernightLab 15:25). First run is SUPERVISED (owner present) before the schedule trusts it.

setlocal
cd /d "C:\path\to"
set LOG=shadow-options-trading-lab\runtime\autonomous_eod.log

echo ================================================================ >> %LOG%
echo [%date% %time%] ATLAS-AutoEOD start >> %LOG%

claude -p "/eodreport  (AUTONOMOUS RUN - report-and-propose mode: you are unattended; the decision core, runner, launchers, config and schemas are deny-ruled read-only. Any fix you would normally apply there becomes a sweep_ledger row with status 'proposed' plus an entry in your morning summary. Allowed writes: docs/EOD_REPORT_CHANGELOG.md, docs/OPTIONS_RESEARCH_QUEUE.json, runtime/lab/**, runtime/memory/**, sweep_ledger appends. End by writing the morning summary to runtime/lab/autonomous_summary_latest.md.)" --settings .claude\autonomous-settings.json --permission-mode acceptEdits >> %LOG% 2>&1

cd /d "C:\path\to\shadow-options-trading-lab"
git add -A >> ..\%LOG% 2>&1
git -c user.name="ATLAS-AutoEOD" -c user.email="atlas-bot@example.com" commit -m "autonomous: nightly eodreport %date%" >> ..\%LOG% 2>&1

echo [%date% %time%] ATLAS-AutoEOD done (exit %errorlevel%) >> ..\%LOG%
exit /b 0
