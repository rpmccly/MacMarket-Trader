@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "DST=C:\Dashboard\MacMarket-Trader"
set "BACKEND_PORT=9510"
set "FRONTEND_PORT=9500"
set "BACKEND_HOST=127.0.0.1"
set "FRONTEND_HOST=127.0.0.1"

if not "%~1"=="" set "DST=%~1"

set "LOG_DIR=%DST%\logs"
set "WEB_DIR=%DST%\apps\web"
set "AGENT_SCHEDULER_LOG=%LOG_DIR%\agent_scheduler.log"
set "AGENT_SCHEDULER_BOOT_LOG=%LOG_DIR%\agent_scheduler_boot.log"

echo.
echo =========================================================
echo Restarting MacMarket-Trader
echo   DST: %DST%
echo =========================================================
echo.

if not exist "%DST%" (
  echo [ERROR] Deployment directory not found:
  echo         %DST%
  pause
  exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

for %%P in (%FRONTEND_PORT% %BACKEND_PORT%) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
    echo [INFO] taskkill /PID %%a on port %%P
    taskkill /F /PID %%a >nul 2>nul
  )
)

powershell -NoProfile -Command "$self=$PID; $dst='%DST%'; $script=$dst + '\scripts\run-agent-mode-scheduler.ps1'; $procs = @(Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $self -and $_.CommandLine -and ($_.CommandLine -like ('*' + $script + '*') -or $_.CommandLine -like '*agent-scheduler-check*') }); foreach($p in $procs){ Write-Host ('[INFO] taskkill /PID ' + $p.ProcessId + ' Agent scheduler'); Start-Process -FilePath taskkill.exe -ArgumentList '/PID', $p.ProcessId, '/F', '/T' -NoNewWindow -Wait }"

echo [INFO] Starting backend...
start "MacMarket-Trader API" /MIN cmd /c "cd /d \"%DST%\" && call .venv\Scripts\activate.bat && python -m uvicorn macmarket_trader.api.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% > \"%LOG_DIR%\backend.log\" 2>&1"

if exist "%WEB_DIR%\package.json" (
  echo [INFO] Starting frontend...
  start "MacMarket-Trader WEB" /MIN cmd /c "cd /d \"%WEB_DIR%\" && npm run start -- --hostname %FRONTEND_HOST% --port %FRONTEND_PORT% > \"%LOG_DIR%\frontend.log\" 2>&1"
)

if exist "%DST%\scripts\run-agent-mode-scheduler.ps1" (
  echo [INFO] Starting Agent Mode scheduler...
  start "MacMarket-Trader Agent Scheduler" /MIN /D "%DST%" cmd /c ""%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%DST%\scripts\run-agent-mode-scheduler.ps1" -RepoPath "%DST%" -Loop >> "%AGENT_SCHEDULER_BOOT_LOG%" 2>&1"
) else (
  echo [WARN] Agent Mode scheduler script not found: %DST%\scripts\run-agent-mode-scheduler.ps1
)

echo [OK] Restart issued.
pause
exit /b 0
