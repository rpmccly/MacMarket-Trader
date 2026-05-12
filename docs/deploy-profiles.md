# Deploy profiles

The canonical operator deploy is `scripts/deploy_windows.bat` (invoked
through the top-level `deploy-macmarket-trader.bat` wrapper). It mirrors
the repo into `C:\Dashboard\MacMarket-Trader`, runs validation tests,
builds the frontend, and restarts the backend + frontend services.

The full deploy keeps running every backend pytest, every frontend
Vitest, and the TypeScript check. It is the **default** and remains the
safe release path. Operators can opt into a faster test profile for
iterative UI / research-only work via `-TestProfile`.

## Supported profiles

| Profile | Backend validation | Frontend validation | When to use |
|---|---|---|---|
| `full` (default) | full backend pytest | full Vitest + tsc | Important release / end-of-day / production change / anything touching ranking, approval, or order paths |
| `fast` | charts + Momentum active guards + Phase C static + deploy temp + deploy profiles | tsc + narrow Vitest subset (chart-history-range, Momentum integration, Phase C2 evidence smoke) | Iterative UI or research-only changes that recently shipped |
| `frontend` | skipped | tsc + full Vitest | Frontend-only changes (component, helper, panel) with no backend file touched |
| `backend` | full backend pytest | tsc only | Backend-only changes (API route, schema, helper) with no rendered UI change |
| `none` (emergency) | skipped | skipped | Operator emergency only. Requires `-ForceNoTests`. Refuses to run when live broker env vars are present. |

`full` is always the default. Profiles are case-insensitive. Unknown
values fail the deploy with a clear error before any tests run.

## Exact commands

```powershell
# Full deploy (default safe path)
.\deploy-macmarket-trader.bat
# or equivalent explicit form:
.\deploy-macmarket-trader.bat -TestProfile full

# Fast smoke deploy (iterative UI / research-only)
.\deploy-macmarket-trader.bat -TestProfile fast

# Frontend-only deploy
.\deploy-macmarket-trader.bat -TestProfile frontend

# Backend-only deploy
.\deploy-macmarket-trader.bat -TestProfile backend

# Emergency no-test deploy (only when -ForceNoTests is supplied AND no
# broker-live env vars are set)
.\deploy-macmarket-trader.bat -TestProfile none -ForceNoTests
```

The DST override remains the first positional argument:

```powershell
.\deploy-macmarket-trader.bat "C:\Dashboard\MacMarket-Trader" -TestProfile fast
```

## Fast profile test set

Backend (`pytest -q -p no:cacheprovider --basetemp <unique> --tb=short`):

- `tests/test_charts_api.py`
- `tests/test_momentum_charts_api.py`
- `tests/test_momentum_b64_queue_response_guard.py`
- `tests/test_momentum_b63_queue_consistency.py`
- `tests/test_momentum_active_delta_scale.py`
- `tests/test_true_momentum_strategy_families.py`
- `tests/test_momentum_phase_closeout.py`
- `tests/test_deploy_test_temp.py`
- `tests/test_deploy_profiles.py`

Frontend (`npx --no-install vitest run`):

- `lib/chart-history-range.test.ts`
- `components/charts/chart-history-range-select.test.tsx`
- `lib/momentum-integration.test.ts`
- `lib/true-momentum-preview-evidence.test.ts`
- `components/recommendations/true-momentum-preview-evidence-panel.test.tsx`

Plus `npx --no-install tsc --noEmit`.

## Frontend / backend profile behavior

- `frontend` runs `tsc --noEmit` + the full Vitest suite via `npm test`,
  and skips the backend pytest entirely.
- `backend` runs the full backend pytest and `tsc --noEmit`, and skips
  the frontend Vitest suite.

Both profiles still build the frontend (`npm run build`) and restart the
backend + frontend services after dependencies install — only the test
phase differs.

## Emergency `none` profile

The `none` profile is reserved for operator emergencies (e.g. a hot-fix
that must ship before any test pass can complete). To prevent silent
misuse it has the following guardrails:

1. Requires `-ForceNoTests` to be explicitly supplied on the command
   line. Without that flag the deploy aborts with exit code 64.
2. Refuses to run when `MACMARKET_BROKER_LIVE=1` or
   `BROKER_PROVIDER=alpaca` is set in the environment. No-test deploy
   must never coincide with live trading.
3. Logs a large `[WARN]` banner stating *"No-test deploy is operator
   emergency mode. It skips validation and should not be used for
   normal releases."*
4. Skips both backend pytest and frontend Vitest **and** the
   `tsc --noEmit` check, but still mirrors the source tree, installs
   dependencies, builds the frontend, and restarts services.

## Deploy-temp hardening preserved

Every profile that invokes pytest:

- Allocates a unique per-run basetemp under
  `%TEMP%\macmarket-pytest-deploy\<timestamp>` via the
  `scripts/deploy_test_temp.ps1` `-Mode New` helper.
- Passes `-p no:cacheprovider` so deploy-time pytest does not race with
  developer-machine pytest caches.
- Cleans stale `macmarket-pytest-deploy` entries older than 1 day and
  the legacy `%TMP_DIR%\pytest-deploy` / `%DST%\.pytest-tmp` directories
  before the run (best-effort).
- Removes its own per-run basetemp after pytest exits (best-effort —
  cleanup failures never mask the test result).

Static tests in `tests/test_deploy_test_temp.py` and
`tests/test_deploy_profiles.py` fail the build if the deploy script
reintroduces the legacy `%TMP_DIR%\pytest-deploy` fixed-path basetemp,
broadly removes the deploy root, or broadly kills Python / Node
processes.

## What this never changes

- **No ranking math change.** `DeterministicRankingEngine` and
  `build_momentum_ranking_contribution` are byte-identical across
  every profile.
- **No queue sorting change.**
- **No recommendation approval, promote, save, paper-order, settle,
  replay, or options-preview behavior change.**
- **No paper-order creation change.** Paper-order creation remains
  manual regardless of selected profile.
- **No active Phase C activation.** Phase C0 / C1 / C2 / C2.1 / C2.2
  surfaces remain research-only.
- **No Thinkorswim parity fixtures landed.** Profile selection has no
  effect on parity-pending posture.

The deploy profile is an operational improvement only — it changes
which tests run before the existing copy / install / build / restart
flow, never the behavior of the deployed system.

## Logging

Every deploy logs the selected profile + the test plan before any
tests run, e.g.:

```
[INFO] Deploying MacMarket-Trader
[INFO]   SRC: C:\Users\ryanm\OneDrive\Documents\GitHub\MacMarket-Trader
[INFO]   DST: C:\Dashboard\MacMarket-Trader
[INFO]   Test profile: fast   (full remains the default safe path)
[INFO]   Backend validation: charts + Momentum active guards + Phase C static + deploy temp
[INFO]   Frontend validation: tsc + chart-history-range + Momentum integration + Phase C2 evidence smoke
```

If the deploy is running without Administrator privileges, a
clear `[WARN] Not running as Administrator…` banner is logged so the
operator knows port / process cleanup may be partial.
