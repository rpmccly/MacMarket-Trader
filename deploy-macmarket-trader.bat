@echo off
setlocal

REM =========================================================
REM  MacMarket-Trader - deploy wrapper
REM
REM  Resolves the repo root strictly from this wrapper's own
REM  location (%~dp0). Never trusts the current working
REM  directory or positional argument values for path
REM  resolution. See docs\deploy-profiles.md "Troubleshooting"
REM  for the SRC-parent-folder bug this guards against.
REM =========================================================

set "REPO_ROOT=%~dp0"
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

if not exist "%REPO_ROOT%\scripts\deploy_windows.bat" (
  echo [ERROR] Wrapper cannot locate scripts\deploy_windows.bat under:
  echo         %REPO_ROOT%
  pause
  exit /b 1
)

REM Detect -DryRun or -ValidateRealPath in the forwarded args so we can
REM skip the trailing pause. Both flags are designed to be safe for
REM automation / unit tests, so the wrapper must not block on input.
set "WRAPPER_DRY_RUN=0"
for %%A in (%*) do (
  if /I "%%~A"=="-DryRun"           set "WRAPPER_DRY_RUN=1"
  if /I "%%~A"=="-ValidateRealPath" set "WRAPPER_DRY_RUN=1"
)

REM Pin the working directory to the repo root before invoking the
REM canonical deploy script. The deploy script ALSO resolves its own
REM source path from its %~dp0 internally; pinning cwd here just makes
REM the diagnostics consistent if the wrapper is invoked from elsewhere.
pushd "%REPO_ROOT%" >nul
call "%REPO_ROOT%\scripts\deploy_windows.bat" %*
set "WRAPPER_RC=%ERRORLEVEL%"
popd >nul

if "%WRAPPER_DRY_RUN%"=="0" pause
exit /b %WRAPPER_RC%
