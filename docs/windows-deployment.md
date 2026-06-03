# Windows Private-Alpha Deployment

Canonical deployment scripts live in `scripts/`.

## Auth provider default for deployment

- Deployment/private-alpha runtime should use Clerk (`AUTH_PROVIDER=clerk`).
- Mock auth is local/test only and is blocked at startup for non-`dev/local/test` environments.

## Canonical scripts

- `scripts/deploy_windows.bat`
- `scripts/restart_windows.bat`
- `scripts/run_backend_dev_windows.bat`
- `scripts/run_frontend_dev_windows.bat`

Root-level batch files are thin wrappers only.

## Canonical directories

- Source checkout: the repo folder where `deploy-macmarket-trader.bat` is run.
- Live runtime target: `C:\Dashboard\MacMarket-Trader`

The deploy wrapper resolves the source checkout from its own file location and
mirrors it into the live runtime target. Runtime state such as `.env`, logs,
SQLite databases, uploads, and generated build folders is preserved.

## Ports

- Frontend: `9500`
- Backend API: `9510`

## Deploy flow (`scripts/deploy_windows.bat`)

1. Stop listeners on ports `9500`/`9510`.
2. Mirror the source checkout into `C:\Dashboard\MacMarket-Trader` while
   preserving runtime state.
3. Create/activate the backend venv and install backend dependencies.
4. Initialize a fresh DB or apply schema updates for an existing DB before
   validation. This is the deployment migration step for additive tables such
   as Agent Mode run/settings audit tables.
5. Run the selected backend and frontend validation profile.
6. Install/build frontend dependencies if present.
7. Restart backend, frontend, and the Agent Mode scheduler loop from the live
   runtime directories and write logs under
   `C:\Dashboard\MacMarket-Trader\logs`.
8. Run backend and frontend health checks before reporting success.

The Agent Mode scheduler is a separate PowerShell loop started by
`scripts/run-agent-mode-scheduler.ps1`. It calls
`python -m macmarket_trader.cli agent-scheduler-check` every five minutes from
`C:\Dashboard\MacMarket-Trader`, using the same deployed `.env`, virtualenv,
and database as the backend. Its logs are:

```powershell
C:\Dashboard\MacMarket-Trader\logs\agent_scheduler.log
C:\Dashboard\MacMarket-Trader\logs\agent_scheduler_boot.log
```

Verify the scheduler after deploy or restart:

```powershell
cd C:\Dashboard\MacMarket-Trader
.\scripts\run-agent-mode-scheduler.ps1 -Once -NoNotifications -DryRun
.\.venv\Scripts\python.exe -m macmarket_trader.cli agent-scheduler-diagnostics
.\.venv\Scripts\python.exe -m macmarket_trader.cli agent-scheduler-check --dry-run --no-notifications
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*run-agent-mode-scheduler.ps1*" -or $_.CommandLine -like "*agent-scheduler-check*" } | Select-Object ProcessId, CommandLine
Get-Content C:\Dashboard\MacMarket-Trader\logs\agent_scheduler.log -Tail 80
```

The foreground `-Once -DryRun -NoNotifications` check creates no paper orders,
suppresses email/SMS digests, prints safe diagnostics, and exits. The
deployment/restart launcher uses `-Loop`; the scheduler writes `HEARTBEAT`,
`DB_DIAGNOSTICS`, `SCHEDULER_CHECK`, and `STARTUP_ERROR` lines so
`agent-scheduler-diagnostics` can report the latest heartbeat/check time,
startup error, scheduler process count, and log last-write time.

## Runtime state safety

Deploy mirror excludes runtime state from destructive replacement, including:
- `.env`
- `.auth/`
- `logs/`
- sqlite files (`*.sqlite`, `*.sqlite3`)
- data/storage/upload directories (`data`, `storage`, `uploads`)

The mirror also excludes local development/test noise so deploys do not copy
AI worktrees, pytest scratch folders, or generated TypeScript incremental
state into the runtime folder. Current Robocopy exclusions include `.auth/`,
`.claude/`, `.pytest-tmp/`, `.tmp/`, and `*.tsbuildinfo`.

`scripts/deploy_windows.bat` recreates an ignored runtime `.tmp/` folder after
mirroring and runs backend pytest with a deployment-local basetemp under
`.tmp/pytest-deploy`. This keeps deployment tests independent from stale source
scratch folders and from machine-wide pytest temp-directory permissions.

## Deployed browser smoke

Authenticated deployed UI smoke is optional release evidence for the
Cloudflare Access protected app. It should use a dedicated smoke user and local
secrets only. From the source checkout:

```powershell
cd apps\web
npm run smoke:deployed
```

Set `CF_ACCESS_CLIENT_ID` / `CF_ACCESS_CLIENT_SECRET` for the Cloudflare Access
service token and/or `SMOKE_AUTH_STORAGE_STATE` for a Playwright storage state.
The smoke is non-mutating by default and writes screenshots plus JSON/Markdown
evidence under `.tmp/evidence/deployed-ui-smoke-*/`. Do not copy `.auth/`
storage-state files into the deployment mirror.

## Fail-fast behavior

Critical commands are guarded with `|| goto :fail` and deployment stops immediately on failure.

## Release checklist

For releases that add ORM models or Alembic migrations, run the normal deploy
wrapper instead of a restart-only script:

```powershell
.\deploy-macmarket-trader.bat "C:\Dashboard\MacMarket-Trader"
```

Use `restart-macmarket-trader.bat` only after the live runtime already has the
current code, dependencies, frontend build, and schema updates. The restart
script now stops stale Agent Mode scheduler loops and starts a fresh scheduler
loop alongside backend and frontend.

## Database migration sanity

The Windows private-alpha runtime at `C:\Dashboard\MacMarket-Trader` uses the
same `DATABASE_URL` as the backend app. In the current deployment profile that
is normally SQLite, and `scripts/deploy_windows.bat` applies the additive
schema step through `macmarket_trader.storage.db.apply_schema_updates()`.

Do not run a manual Alembic command unless you have first confirmed the
database target from the live runtime:

```powershell
cd C:\Dashboard\MacMarket-Trader
.\.venv\Scripts\python.exe -m macmarket_trader.cli db-diagnostics
```

The diagnostic prints the database dialect and redacted URL only. It does not
print database passwords, provider secrets, Twilio secrets, or API keys.

`python -m alembic upgrade head` is not required for the normal Windows deploy
flow. If an operator intentionally runs Alembic, `alembic/env.py` now reads the
app-configured `DATABASE_URL` instead of the old local Postgres fallback.
