@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM =========================================================
REM  MacMarket-Trader - deploy_windows.bat
REM
REM  Canonical deploy entrypoint. See docs\deploy-profiles.md
REM  for the supported test profiles. Default is "full" - the
REM  full backend pytest + full frontend Vitest + tsc safety
REM  net used for every production release. Other profiles are
REM  faster smoke paths for iterative work and must be selected
REM  explicitly with -TestProfile <profile>.
REM =========================================================

REM ---------------------------------------------------------
REM Step 1. Capture the script directory and source root
REM BEFORE any shift / arg parsing happens. Plain `shift` in
REM batch can rotate %0 in addition to %1+, which makes a
REM later `%~dp0..` resolve against the current working
REM directory or a positional arg value instead of the script
REM location. Pinning SRC up-front from %~dp0 avoids that
REM class of bug (see docs\deploy-profiles.md troubleshooting).
REM ---------------------------------------------------------
set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
for %%I in ("%SCRIPT_DIR%\..") do set "SRC=%%~fI"

set "DST=C:\Dashboard\MacMarket-Trader"
set "BACKEND_PORT=9510"
set "FRONTEND_PORT=9500"
set "BACKEND_HOST=localhost"
set "FRONTEND_HOST=localhost"
set "EXPECTED_NODE_MAJOR=v20"
set "EXPECTED_NODE_DISPLAY=any supported v20.x release"
set "RUN_TESTS=1"
set "RUN_E2E=0"
set "STRICT_NODE=0"

REM -------- Argument defaults --------
REM Default profile remains "full" (the historic safe path).
REM -ForceNoTests, -DryRun, -ValidateRealPath are additive opt-in flags.
set "TEST_PROFILE=full"
set "FORCE_NO_TESTS=0"
set "DRY_RUN=0"
set "VALIDATE_REAL_PATH=0"

REM ---------------------------------------------------------
REM Step 2. Goto-based argument parser.
REM
REM We deliberately avoid parenthesized IF blocks here because
REM batch pre-parses the body of an IF block, and any value
REM containing a literal `)` (for example a string like
REM "(emergency)") can prematurely close the block and produce
REM the classic "... was unexpected at this time." parse error.
REM Each flag has its own :HANDLE_* label, and unknown args
REM fall through to the positional DST override.
REM ---------------------------------------------------------
:PARSE_ARGS
if "%~1"=="" goto :PARSE_ARGS_DONE
if /I "%~1"=="-TestProfile"      goto :HANDLE_TESTPROFILE
if /I "%~1"=="-Profile"          goto :HANDLE_TESTPROFILE
if /I "%~1"=="-ForceNoTests"     goto :HANDLE_FORCENOTESTS
if /I "%~1"=="-DryRun"           goto :HANDLE_DRYRUN
if /I "%~1"=="-ValidateRealPath" goto :HANDLE_VALIDATEREALPATH
if /I "%~1"=="-Help"             goto :HANDLE_HELP
if /I "%~1"=="/?"                goto :HANDLE_HELP
REM Fallthrough: treat as positional DST override (first non-flag arg).
set "DST=%~1"
shift
goto :PARSE_ARGS

:HANDLE_TESTPROFILE
if "%~2"=="" goto :ERR_TESTPROFILE_MISSING
set "TEST_PROFILE=%~2"
shift
shift
goto :PARSE_ARGS

:HANDLE_FORCENOTESTS
set "FORCE_NO_TESTS=1"
shift
goto :PARSE_ARGS

:HANDLE_DRYRUN
set "DRY_RUN=1"
shift
goto :PARSE_ARGS

:HANDLE_VALIDATEREALPATH
set "VALIDATE_REAL_PATH=1"
shift
goto :PARSE_ARGS

:HANDLE_HELP
echo Usage: deploy-macmarket-trader.bat [^<DST^>] [-TestProfile full^|fast^|frontend^|backend^|none] [-ForceNoTests] [-DryRun] [-ValidateRealPath]
echo.
echo Default profile is "full" (full backend pytest + full Vitest + tsc).
echo Use -DryRun to print the resolved deploy plan and exit without changes.
echo Use -ValidateRealPath to exercise the post-schema test-plan branching
echo without performing mirror/install/test/build/restart side effects.
exit /b 0

:ERR_TESTPROFILE_MISSING
echo [ERROR] -TestProfile requires a value: full, fast, frontend, backend, or none
exit /b 64

:PARSE_ARGS_DONE

REM Normalize test profile to lower-case via a powershell call. Strict
REM whitelist enforced below.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "$p = '%TEST_PROFILE%'; if ($p) { $p.Trim().ToLowerInvariant() } else { 'full' }"`) do set "TEST_PROFILE=%%P"
if not defined TEST_PROFILE set "TEST_PROFILE=full"

set "VALID_PROFILE=0"
if /I "%TEST_PROFILE%"=="full"     set "VALID_PROFILE=1"
if /I "%TEST_PROFILE%"=="fast"     set "VALID_PROFILE=1"
if /I "%TEST_PROFILE%"=="frontend" set "VALID_PROFILE=1"
if /I "%TEST_PROFILE%"=="backend"  set "VALID_PROFILE=1"
if /I "%TEST_PROFILE%"=="none"     set "VALID_PROFILE=1"

if "%VALID_PROFILE%"=="0" goto :ERR_UNKNOWN_PROFILE
if /I "%TEST_PROFILE%"=="none" goto :CHECK_NONE_GUARDS
goto :AFTER_PROFILE_GUARDS

:ERR_UNKNOWN_PROFILE
echo [ERROR] Unknown test profile: %TEST_PROFILE%
echo [ERROR] Allowed: full, fast, frontend, backend, or none
exit /b 64

:CHECK_NONE_GUARDS
if "%FORCE_NO_TESTS%"=="0"           goto :ERR_NONE_REQUIRES_FORCE
if /I "%MACMARKET_BROKER_LIVE%"=="1" goto :ERR_NONE_BROKER_LIVE
if /I "%BROKER_PROVIDER%"=="alpaca"  goto :ERR_NONE_ALPACA
echo.
echo =========================================================
echo  [WARN] No-test deploy is operator emergency mode. It skips validation
echo  [WARN] and should not be used for normal releases. Continuing because
echo  [WARN] -ForceNoTests was explicitly supplied.
echo =========================================================
echo.
goto :AFTER_PROFILE_GUARDS

:ERR_NONE_REQUIRES_FORCE
echo [ERROR] The "none" test profile requires -ForceNoTests to run.
echo [ERROR] No-test deploy is operator emergency mode. It skips validation and
echo [ERROR] should not be used for normal releases.
exit /b 64

:ERR_NONE_BROKER_LIVE
echo [ERROR] Refusing -TestProfile none while MACMARKET_BROKER_LIVE=1 is set.
exit /b 64

:ERR_NONE_ALPACA
echo [ERROR] Refusing -TestProfile none while BROKER_PROVIDER=alpaca is set.
exit /b 64

:AFTER_PROFILE_GUARDS

set "LOG_DIR=%DST%\logs"
set "DATA_DIR=%DST%\data"
set "STORAGE_DIR=%DST%\storage"
set "UPLOAD_DIR=%DST%\uploads"
set "TMP_DIR=%DST%\.tmp"
set "WEB_DIR=%DST%\apps\web"
set "BACKEND_LOG=%LOG_DIR%\backend.log"
set "FRONTEND_LOG=%LOG_DIR%\frontend.log"

set "RC=0"

set "KILLPAT_API=*%DST%\.venv\Scripts\python.exe*-m uvicorn*macmarket_trader.api.main:app*"
set "KILLPAT_WEB=*%DST%\apps\web*next*start*"

REM ---------------------------------------------------------
REM Per-profile test-plan summary printed before any tests run.
REM Single-line IF set statements only - never wrap parens
REM around values that might themselves contain parens.
REM ---------------------------------------------------------
set "PROFILE_BACKEND_DESC=full backend pytest"
set "PROFILE_FRONTEND_DESC=full Vitest + tsc"
if /I "%TEST_PROFILE%"=="fast"     set "PROFILE_BACKEND_DESC=charts + Momentum active guards + Phase C static + deploy temp"
if /I "%TEST_PROFILE%"=="fast"     set "PROFILE_FRONTEND_DESC=tsc + chart-history-range + Momentum integration + Phase C2 evidence smoke"
if /I "%TEST_PROFILE%"=="frontend" set "PROFILE_BACKEND_DESC=skipped"
if /I "%TEST_PROFILE%"=="frontend" set "PROFILE_FRONTEND_DESC=tsc + full Vitest"
if /I "%TEST_PROFILE%"=="backend"  set "PROFILE_BACKEND_DESC=full backend pytest"
if /I "%TEST_PROFILE%"=="backend"  set "PROFILE_FRONTEND_DESC=tsc only"
if /I "%TEST_PROFILE%"=="none"     set "PROFILE_BACKEND_DESC=SKIPPED [emergency]"
if /I "%TEST_PROFILE%"=="none"     set "PROFILE_FRONTEND_DESC=SKIPPED [emergency]"

echo.
echo =========================================================
echo Deploying MacMarket-Trader
echo   SRC: %SRC%
echo   DST: %DST%
echo   Test profile: %TEST_PROFILE%   [full remains the default safe path]
echo   Backend validation: %PROFILE_BACKEND_DESC%
echo   Frontend validation: %PROFILE_FRONTEND_DESC%
echo   RUN_TESTS: %RUN_TESTS%
echo   RUN_E2E : %RUN_E2E%
echo   DryRun  : %DRY_RUN%
echo   ValidateRealPath: %VALIDATE_REAL_PATH%
echo =========================================================
echo.

REM ---------------------------------------------------------
REM Validate SRC. If validation fails we print diagnostic
REM context (script dir, cwd, args) so the operator can find
REM the wrapper bug, then exit non-zero.
REM ---------------------------------------------------------
call :STEP "validate-source-root"
call :VALIDATE_SRC
if errorlevel 1 (
  set "RC=1"
  goto :END
)

if "%DRY_RUN%"=="1" goto :DRY_RUN_EXIT

REM ---------------------------------------------------------
REM Side-effectful pre-test phase. Skipped under
REM -ValidateRealPath so the test-plan branching below can be
REM exercised without touching processes, the filesystem, or
REM the deployed venv / database.
REM ---------------------------------------------------------
if "%VALIDATE_REAL_PATH%"=="1" goto :POST_SCHEMA_PLAN

call :STEP "admin-check"
set "IS_ADMIN=0"
net session >nul 2>&1
if errorlevel 1 (
  echo [WARN] Not running as Administrator. Continuing, but port/process cleanup may be limited.
  echo [WARN] Stale child python/node processes from a previous run can keep .tmp\pytest-deploy
  echo [WARN] and .pytest_cache directories locked. If deploy tests fail with WinError 5
  echo [WARN] PermissionError, close prior backend/frontend windows or rerun from an
  echo [WARN] elevated PowerShell.
) else (
  echo [INFO] Running with Administrator privileges.
  set "IS_ADMIN=1"
)

call :STEP "ensure-deploy-dirs"
if not exist "%DST%" mkdir "%DST%" >nul 2>&1
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%" >nul 2>&1
if not exist "%STORAGE_DIR%" mkdir "%STORAGE_DIR%" >nul 2>&1
if not exist "%UPLOAD_DIR%" mkdir "%UPLOAD_DIR%" >nul 2>&1
if not exist "%TMP_DIR%" mkdir "%TMP_DIR%" >nul 2>&1

call :STEP "node-version-check"
call :CheckNode
if errorlevel 1 (
  set "RC=1"
  goto :END
)

call :STEP "stop-services"
echo [INFO] Stopping listeners on %FRONTEND_PORT% / %BACKEND_PORT%...
call :StopPort "%FRONTEND_PORT%"
call :StopPort "%BACKEND_PORT%"
call :KillByCmdLine "%KILLPAT_API%"
call :KillByCmdLine "%KILLPAT_WEB%"
REM Brief grace period for OS to release sockets/handles, then one retry pass.
timeout /t 2 /nobreak >nul
call :StopPort "%FRONTEND_PORT%"
call :StopPort "%BACKEND_PORT%"

echo.
call :STEP "mirror-sources"
if /I "%SRC%"=="%DST%" goto :SKIP_MIRROR

echo [INFO] Mirroring repo to deployment folder [preserving runtime artifacts]
robocopy "%SRC%" "%DST%" /MIR /R:2 /W:2 /FFT /Z /NP ^
  /XD ".git" ".venv" "__pycache__" ".pytest_cache" ".pytest-tmp" ".mypy_cache" ".ruff_cache" ^
      ".auth" ".claude" ".tmp" ^
      "logs" "uploads" "backups" ^
      "node_modules" ".next" "dist" "build" "playwright-report" "test-results" ^
      ".clerk" "apps\web\node_modules" "apps\web\.next" ^
  /XF ".env" ".env.local" "*.log" "*.pyc" "*.pyo" "*.sqlite" "*.sqlite3" "*.db" "*.tsbuildinfo"

set "ROBO=%ERRORLEVEL%"
if %ROBO% GEQ 8 (
  echo [ERROR] Robocopy failed with code %ROBO%.
  set "RC=%ROBO%"
  goto :END
)
goto :AFTER_MIRROR

:SKIP_MIRROR
echo [INFO] Source and destination are the same. Skipping mirror step.

:AFTER_MIRROR

echo.
if not exist "%DST%\.env" (
  echo [WARN] %DST%\.env not found. Backend may fail until runtime env is created.
)
if exist "%WEB_DIR%\package.json" if not exist "%WEB_DIR%\.env.local" (
  echo [WARN] %WEB_DIR%\.env.local not found. Frontend may fail until runtime env is created.
)

call :STEP "venv-create"
echo [INFO] Creating or reusing Python virtual environment...
if not exist "%DST%\.venv\Scripts\python.exe" (
  py -3.13 -m venv "%DST%\.venv"
  if errorlevel 1 (
    echo [ERROR] Failed to create Python 3.13 venv.
    set "RC=1"
    goto :END
  )
)
call "%DST%\.venv\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] Failed to activate venv.
  set "RC=1"
  goto :END
)

pushd "%DST%"
call :STEP "backend-deps-install"
echo [INFO] Installing backend dependencies...
python -m pip install --upgrade pip
if errorlevel 1 (
  set "RC=1"
  goto :FAIL_POP
)
pip install -e ".[dev]"
if errorlevel 1 (
  echo [ERROR] Backend dependency install failed.
  set "RC=1"
  goto :FAIL_POP
)

call :STEP "database-check"
echo [INFO] Checking database state...
if not exist "%DST%\macmarket_trader.db" goto :DB_INIT
echo [INFO] Existing database found. Applying schema updates...
call :STEP "schema-update"
python -c "from macmarket_trader.storage.db import apply_schema_updates; added = apply_schema_updates(); print('[INFO] Schema columns added:', added) if added else print('[INFO] Schema already current.')"
if errorlevel 1 (
  echo [ERROR] Schema update failed.
  set "RC=1"
  goto :FAIL_POP
)
goto :AFTER_DB_PHASE

:DB_INIT
echo [INFO] No existing database found. Initializing fresh schema...
call :STEP "schema-init"
python -c "from macmarket_trader.storage.db import init_db; init_db()"
if errorlevel 1 (
  echo [ERROR] Database initialization failed.
  set "RC=1"
  goto :FAIL_POP
)

:AFTER_DB_PHASE

REM ---------------------------------------------------------
REM POST-SCHEMA: test-plan branching. This is the section
REM that previously failed with "... was unexpected at this
REM time." because of unescaped `(...)` text inside
REM parenthesized IF blocks. The fix is to keep the per-
REM profile decisions linear (single-line IF) and push every
REM real command into a subroutine that is called from a
REM top-level statement (not from inside a parenthesized
REM block body).
REM ---------------------------------------------------------

:POST_SCHEMA_PLAN

call :STEP "backend-validation-plan"
set "RUN_BACKEND_TESTS=1"
if /I "%TEST_PROFILE%"=="frontend" set "RUN_BACKEND_TESTS=0"
if /I "%TEST_PROFILE%"=="none"     set "RUN_BACKEND_TESTS=0"
if "%RUN_TESTS%"=="0"              set "RUN_BACKEND_TESTS=0"

if "%RUN_BACKEND_TESTS%"=="1" echo [INFO] Backend validation plan: %PROFILE_BACKEND_DESC%
if "%RUN_BACKEND_TESTS%"=="0" call :LOG_BACKEND_SKIP_REASON

if "%VALIDATE_REAL_PATH%"=="1" goto :FRONTEND_PLAN
if "%RUN_BACKEND_TESTS%"=="0"  goto :FRONTEND_PLAN

call :RUN_BACKEND_VALIDATION
if errorlevel 1 (
  set "RC=1"
  goto :FAIL_POP
)

:FRONTEND_PLAN
call :STEP "frontend-validation-plan"
set "FRONTEND_PRESENT=0"
if exist "%WEB_DIR%\package.json" set "FRONTEND_PRESENT=1"

set "RUN_FRONTEND_TESTS=1"
set "RUN_FRONTEND_TSC=1"
if /I "%TEST_PROFILE%"=="backend" set "RUN_FRONTEND_TESTS=0"
if /I "%TEST_PROFILE%"=="none"    set "RUN_FRONTEND_TESTS=0"
if /I "%TEST_PROFILE%"=="none"    set "RUN_FRONTEND_TSC=0"
if "%RUN_TESTS%"=="0"             set "RUN_FRONTEND_TESTS=0"

if "%FRONTEND_PRESENT%"=="1" echo [INFO] Frontend validation plan: %PROFILE_FRONTEND_DESC%
if "%FRONTEND_PRESENT%"=="0" echo [INFO] Frontend skipped: %WEB_DIR%\package.json not found.

if "%VALIDATE_REAL_PATH%"=="1" goto :PLAN_REPORT_DONE
if "%FRONTEND_PRESENT%"=="0"   goto :START_SERVICES

call :FRONTEND_PHASE
if errorlevel 1 goto :FAIL_POP

:START_SERVICES
call :STEP "restart-services"
if "%VALIDATE_REAL_PATH%"=="1" goto :PLAN_REPORT_DONE

echo.
echo [INFO] Starting backend...
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
start "MacMarket-Trader API" /MIN /D "%DST%" cmd /c ""%DST%\.venv\Scripts\python.exe" -m uvicorn macmarket_trader.api.main:app --host %BACKEND_HOST% --port %BACKEND_PORT% >> "%BACKEND_LOG%" 2>&1"

if exist "%WEB_DIR%\package.json" (
  echo [INFO] Starting frontend...
  timeout /t 5 /nobreak >nul
  start "MacMarket-Trader WEB" /MIN /D "%WEB_DIR%" cmd /c "npm.cmd run start -- --hostname 0.0.0.0 --port %FRONTEND_PORT% >> "%FRONTEND_LOG%" 2>&1"
)

call :STEP "health-checks"
echo [INFO] Waiting for backend health...
timeout /t 10 /nobreak >nul
call :WaitForHttp "http://%BACKEND_HOST%:%BACKEND_PORT%/health" "backend /health" "180"
if errorlevel 1 (
  echo [ERROR] Backend health check did not pass in time.
  call :ShowLogTail "%BACKEND_LOG%" "backend"
  set "RC=1"
  goto :POPD_END
)

if exist "%WEB_DIR%\package.json" (
  echo [INFO] Waiting for frontend root...
  call :WaitForHttp "http://127.0.0.1:%FRONTEND_PORT%/sign-in" "frontend sign-in" "300"
  if errorlevel 1 (
    echo [ERROR] Frontend did not respond in time.
    call :ShowLogTail "%FRONTEND_LOG%" "frontend"
    set "RC=1"
    goto :POPD_END
  )
)

echo.
echo [OK] Deployment completed successfully.

schtasks /query /tn "MacMarket-StrategyScheduler" >nul 2>&1
if errorlevel 1 (
  echo [WARN] Strategy scheduler task not registered.
  echo [WARN] See runbook Section - Scheduled report runner to set it up.
)

:POPD_END
popd
goto :END

:PLAN_REPORT_DONE
call :STEP "validate-real-path-exit"
echo.
echo [INFO] -ValidateRealPath: post-schema test-plan branching exercised
echo [INFO]   without performing mirror, install, test, build, or restart.
echo [INFO]   This run intentionally skips all real side effects.
exit /b 0

:DRY_RUN_EXIT
echo [INFO] -DryRun supplied. Resolved deploy plan printed above. Exiting
echo [INFO] without mirroring, installing, testing, building, or restarting.
exit /b 0

:FAIL_POP_WEB
popd

:FAIL_POP
popd
goto :END

REM ---------------------------------------------------------
REM Subroutines. Kept out of any top-level parenthesized
REM block so any `(...)` text inside them cannot miscount the
REM caller's block parens.
REM ---------------------------------------------------------

:STEP
echo [STEP] %~1
exit /b 0

:VALIDATE_SRC
set "SRC_OK=1"
if not exist "%SRC%\README.md"             set "SRC_OK=0"
if not exist "%SRC%\pyproject.toml"        set "SRC_OK=0"
if not exist "%SRC%\apps\web"              set "SRC_OK=0"
if not exist "%SRC%\src\macmarket_trader"  set "SRC_OK=0"
if "%SRC_OK%"=="0" (
  echo [ERROR] Source path does not look like the MacMarket repo:
  echo         SRC          = %SRC%
  echo         SCRIPT_DIR   = %SCRIPT_DIR%
  echo         CWD          = %CD%
  echo         TEST_PROFILE = %TEST_PROFILE%
  echo         DRY_RUN      = %DRY_RUN%
  echo         VALIDATE_REAL_PATH = %VALIDATE_REAL_PATH%
  echo [ERROR] Required entries: README.md, pyproject.toml, apps\web, src\macmarket_trader
  exit /b 1
)
if not exist "%SRC%\apps\web\package.json" (
  echo [WARN] apps\web\package.json not found in source. Frontend steps will be skipped.
)
exit /b 0

:LOG_BACKEND_SKIP_REASON
if /I "%TEST_PROFILE%"=="frontend" goto :LOG_BACKEND_SKIP_FE
if /I "%TEST_PROFILE%"=="none"     goto :LOG_BACKEND_SKIP_NONE
echo [INFO] Backend tests skipped. Set RUN_TESTS=1 to enable them.
exit /b 0
:LOG_BACKEND_SKIP_FE
echo [INFO] Backend tests skipped: -TestProfile frontend.
exit /b 0
:LOG_BACKEND_SKIP_NONE
echo [WARN] Backend tests skipped: -TestProfile none [emergency].
exit /b 0

:LOG_FRONTEND_SKIP_REASON
if /I "%TEST_PROFILE%"=="backend" goto :LOG_FRONTEND_SKIP_BE
if /I "%TEST_PROFILE%"=="none"    goto :LOG_FRONTEND_SKIP_NONE
echo [INFO] Frontend unit tests skipped. Set RUN_TESTS=1 to enable them.
exit /b 0
:LOG_FRONTEND_SKIP_BE
echo [INFO] Frontend Vitest skipped: -TestProfile backend.
exit /b 0
:LOG_FRONTEND_SKIP_NONE
echo [WARN] Frontend Vitest skipped: -TestProfile none [emergency].
exit /b 0

REM ---------------------------------------------------------
REM Backend validation runner. Lives in its own subroutine so
REM the nested IF/FOR/parenthesized blocks for temp setup and
REM pytest dispatch cannot interfere with the main-flow IF
REM block parsing.
REM ---------------------------------------------------------
:RUN_BACKEND_VALIDATION
call :STEP "backend-validation-prep"
echo [INFO] Preparing deploy-test temp area...
REM Best-effort: clean stale macmarket-pytest-deploy entries older than 1 day.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\deploy_test_temp.ps1" -Mode CleanStale -MaxAgeDays 1 >nul 2>&1

REM Best-effort: remove any lingering deploy-local fixed temp folder from
REM older deploy versions. This is the path that caused WinError 5 in
REM deploys prior to the per-run temp fix.
if exist "%TMP_DIR%\pytest-deploy" powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\deploy_test_temp.ps1" -Mode Remove -Path "%TMP_DIR%\pytest-deploy" >nul 2>&1
if exist "%DST%\.pytest-tmp"      powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\deploy_test_temp.ps1" -Mode Remove -Path "%DST%\.pytest-tmp" >nul 2>&1

REM Allocate a unique per-run basetemp under %TEMP%\macmarket-pytest-deploy.
set "DEPLOY_PYTEST_BASETEMP="
for /f "usebackq delims=" %%T in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\deploy_test_temp.ps1" -Mode New`) do set "DEPLOY_PYTEST_BASETEMP=%%T"
if not defined DEPLOY_PYTEST_BASETEMP set "DEPLOY_PYTEST_BASETEMP=%TEMP%\macmarket-pytest-deploy-fallback"
if not exist "%DEPLOY_PYTEST_BASETEMP%" mkdir "%DEPLOY_PYTEST_BASETEMP%" >nul 2>&1

call :STEP "backend-validation-run"
echo [INFO] Running backend tests - profile %TEST_PROFILE%
echo [INFO]   basetemp: %DEPLOY_PYTEST_BASETEMP%
echo [INFO]   pytest cache provider disabled for deploy run.

if /I "%TEST_PROFILE%"=="fast" goto :RUN_BACKEND_FAST
pytest -q -p no:cacheprovider --basetemp "%DEPLOY_PYTEST_BASETEMP%"
set "PYTEST_RC=%ERRORLEVEL%"
goto :RUN_BACKEND_CLEANUP

:RUN_BACKEND_FAST
echo [INFO]   target: charts + Momentum guards + Phase C static + deploy temp
pytest -q -p no:cacheprovider --basetemp "%DEPLOY_PYTEST_BASETEMP%" --tb=short ^
  tests\test_charts_api.py ^
  tests\test_momentum_charts_api.py ^
  tests\test_momentum_b64_queue_response_guard.py ^
  tests\test_momentum_b63_queue_consistency.py ^
  tests\test_momentum_active_delta_scale.py ^
  tests\test_true_momentum_strategy_families.py ^
  tests\test_momentum_phase_closeout.py ^
  tests\test_deploy_test_temp.py ^
  tests\test_deploy_profiles.py
set "PYTEST_RC=%ERRORLEVEL%"

:RUN_BACKEND_CLEANUP
REM Best-effort cleanup after the run. Cleanup failures must not mask the
REM test result, so we always honour PYTEST_RC for the deploy exit code.
powershell -NoProfile -ExecutionPolicy Bypass -File "%SRC%\scripts\deploy_test_temp.ps1" -Mode Remove -Path "%DEPLOY_PYTEST_BASETEMP%" >nul 2>&1

if "%PYTEST_RC%"=="0" exit /b 0
echo [ERROR] Backend tests failed.
exit /b 1

REM ---------------------------------------------------------
REM Frontend phase orchestrator. Runs from a fresh pushd into
REM the web dir so subroutines can assume cwd is %WEB_DIR%.
REM ---------------------------------------------------------
:FRONTEND_PHASE
pushd "%WEB_DIR%"
call :INSTALL_FRONTEND_DEPS
if errorlevel 1 goto :FRONTEND_PHASE_FAIL

call :BUILD_FRONTEND
if errorlevel 1 goto :FRONTEND_PHASE_FAIL

if "%RUN_FRONTEND_TSC%"=="1" call :RUN_TYPESCRIPT_CHECK
if "%RUN_FRONTEND_TSC%"=="0" echo [WARN] TypeScript check skipped: -TestProfile %TEST_PROFILE%.
if errorlevel 1 goto :FRONTEND_PHASE_FAIL

if "%RUN_FRONTEND_TESTS%"=="1" call :RUN_FRONTEND_VALIDATION
if "%RUN_FRONTEND_TESTS%"=="0" call :LOG_FRONTEND_SKIP_REASON
if errorlevel 1 goto :FRONTEND_PHASE_FAIL

if "%RUN_E2E%"=="1" call :RUN_PLAYWRIGHT
if "%RUN_E2E%"=="0" echo [INFO] Playwright E2E skipped. Set RUN_E2E=1 to enable them.
if errorlevel 1 goto :FRONTEND_PHASE_FAIL

popd
exit /b 0

:FRONTEND_PHASE_FAIL
popd
exit /b 1

:INSTALL_FRONTEND_DEPS
call :STEP "frontend-deps-install"
echo.
echo [INFO] Installing frontend dependencies...
if exist "package-lock.json" goto :FE_DEPS_CI
call npm install
goto :FE_DEPS_FALLBACK
:FE_DEPS_CI
call npm ci
:FE_DEPS_FALLBACK
if not errorlevel 1 exit /b 0
echo [WARN] Clean frontend install failed. Retrying with legacy peer dependency resolution...
call npm install --legacy-peer-deps
if not errorlevel 1 exit /b 0
echo [ERROR] Frontend dependency install failed.
exit /b 1

:BUILD_FRONTEND
call :STEP "frontend-build"
echo [INFO] Building frontend...
call npm run build
if errorlevel 1 (
  echo [ERROR] Frontend build failed.
  exit /b 1
)
exit /b 0

:RUN_TYPESCRIPT_CHECK
call :STEP "frontend-tsc"
echo [INFO] Running TypeScript check - tsc --noEmit
call npx --no-install tsc --noEmit
if errorlevel 1 (
  echo [ERROR] TypeScript check failed.
  exit /b 1
)
exit /b 0

:RUN_FRONTEND_VALIDATION
call :STEP "frontend-tests-run"
if /I "%TEST_PROFILE%"=="fast" goto :RUN_FRONTEND_FAST
echo [INFO] Running full frontend unit tests...
call npm test
goto :RUN_FRONTEND_AFTER

:RUN_FRONTEND_FAST
echo [INFO] Running fast frontend Vitest subset...
call npx --no-install vitest run ^
  lib/chart-history-range.test.ts ^
  components/charts/chart-history-range-select.test.tsx ^
  lib/momentum-integration.test.ts ^
  lib/true-momentum-preview-evidence.test.ts ^
  components/recommendations/true-momentum-preview-evidence-panel.test.tsx

:RUN_FRONTEND_AFTER
if errorlevel 1 (
  echo [ERROR] Frontend unit tests failed.
  exit /b 1
)
exit /b 0

:RUN_PLAYWRIGHT
call :STEP "playwright"
echo [INFO] Installing Playwright browsers...
call npx playwright install
if errorlevel 1 (
  echo [ERROR] Playwright browser install failed.
  exit /b 1
)
echo [INFO] Running Playwright E2E...
call npm run test:e2e
if errorlevel 1 (
  echo [ERROR] Playwright E2E failed.
  exit /b 1
)
exit /b 0

:CheckNode
for /f %%V in ('node -v 2^>nul') do set "NODE_VER=%%V"
if not defined NODE_VER (
  echo [ERROR] Node was not found on PATH.
  exit /b 1
)
if /I "!NODE_VER:~0,3!"=="%EXPECTED_NODE_MAJOR%" (
  echo [INFO] Node version OK: !NODE_VER!
  exit /b 0
)

echo [WARN] Node version mismatch: found !NODE_VER!, expected %EXPECTED_NODE_DISPLAY%.
if "%STRICT_NODE%"=="1" (
  echo [ERROR] STRICT_NODE=1, refusing to continue.
  exit /b 1
)
echo [WARN] Continuing because STRICT_NODE=0. For reliable verification, use a supported Node 20.x version.
exit /b 0

:StopPort
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%~1 .*LISTENING"') do (
  echo [INFO] taskkill /PID %%P on port %~1
  taskkill /F /PID %%P >nul 2>nul
)
exit /b 0

:KillByCmdLine
set "PAT=%~1"
if "%PAT%"=="" exit /b 0
powershell -NoProfile -Command "$pat='%PAT%'; $procs = @(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine -like $pat }); foreach($p in $procs){ Write-Host ('[INFO] taskkill /PID ' + $p.ProcessId); Start-Process -FilePath taskkill.exe -ArgumentList '/PID', $p.ProcessId, '/F', '/T' -NoNewWindow -Wait }"
exit /b 0

:WaitForHttp
set "URL=%~1"
set "LABEL=%~2"
set "TIMEOUT=%~3"
powershell -NoProfile -Command ^
  "$url = '%URL%';" ^
  "$label = '%LABEL%';" ^
  "$deadline = (Get-Date).AddSeconds([int]'%TIMEOUT%');" ^
  "do {" ^
  "  try {" ^
  "    $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5;" ^
  "    if($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500) {" ^
  "      Write-Host ('[INFO] HTTP ready: ' + $label + ' -> ' + $resp.StatusCode);" ^
  "      exit 0" ^
  "    }" ^
  "  } catch { Start-Sleep -Seconds 1 }" ^
  "} while((Get-Date) -lt $deadline);" ^
  "exit 1"
exit /b %errorlevel%

:ShowLogTail
set "LOG_FILE=%~1"
set "LOG_LABEL=%~2"
if exist "%LOG_FILE%" (
  echo [INFO] Last %LOG_LABEL% log lines:
  powershell -NoProfile -Command "Get-Content -Path '%LOG_FILE%' -Tail 50"
) else (
  echo [WARN] %LOG_LABEL% log file not found: %LOG_FILE%
)
exit /b 0

:END
echo.
echo Deployment exit code: %RC%
pause
exit /b %RC%
