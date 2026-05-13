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

The `-Profile` alias is equivalent to `-TestProfile`:

```powershell
.\deploy-macmarket-trader.bat -Profile fast
```

The DST override remains the first positional argument:

```powershell
.\deploy-macmarket-trader.bat "C:\Dashboard\MacMarket-Trader" -TestProfile fast
```

## Dry-run mode

`-DryRun` parses arguments, resolves SRC and DST, validates the source
path, prints the banner + test plan, and exits 0 **without** mirroring,
installing, testing, building, or restarting. It is the safe way to
validate that argument forwarding and source-path resolution work
correctly on a given machine before a real deploy:

```powershell
.\deploy-macmarket-trader.bat -DryRun
.\deploy-macmarket-trader.bat -TestProfile fast -DryRun
.\deploy-macmarket-trader.bat -TestProfile full -DryRun
```

`-DryRun` also skips the trailing `pause` in the wrapper so the dry-run
is safe to invoke from automation / unit tests.

## Post-schema validation mode (`-ValidateRealPath`)

`-DryRun` exits before the real deploy phase (mirror / install / schema
update / tests / build / restart). That is the right behaviour for
checking source-path resolution, but it cannot catch parser errors in
the post-schema test-plan branches.

`-ValidateRealPath` exercises the **same test-plan branching that runs
after schema update in a real deploy**, but skips every side-effectful
step (mirror, venv setup, pip install, schema apply, pytest, npm
install, npm build, tsc, vitest, playwright, service start, health
checks). It exists so a subprocess test (or an operator on a fresh
machine) can confirm that the post-schema parser path is balanced and
the per-profile branching resolves correctly, without touching any
shared state:

```powershell
.\deploy-macmarket-trader.bat -ValidateRealPath
.\deploy-macmarket-trader.bat -TestProfile fast -ValidateRealPath
.\deploy-macmarket-trader.bat -TestProfile full -ValidateRealPath
.\deploy-macmarket-trader.bat -TestProfile frontend -ValidateRealPath
.\deploy-macmarket-trader.bat -TestProfile backend -ValidateRealPath
```

Each invocation prints the resolved banner, the validation plan, a
`[STEP] backend-validation-plan` / `[STEP] frontend-validation-plan`
trace, and exits 0. If the parser cannot balance the script the run
will fail with `... was unexpected at this time.` — surfacing the bug
before any side effects happen.

`-ValidateRealPath` also skips the wrapper's trailing `pause`, so it is
safe to call from automation.

## Step tracing

Every deploy emits `[STEP] <name>` lines from a lightweight `:STEP`
subroutine so that the next failure tells us which phase died:

```
[STEP] validate-source-root
[STEP] admin-check
[STEP] ensure-deploy-dirs
[STEP] node-version-check
[STEP] stop-services
[STEP] mirror-sources
[STEP] venv-create
[STEP] backend-deps-install
[STEP] database-check
[STEP] schema-update            (or schema-init on a fresh DB)
[STEP] backend-validation-plan
[STEP] backend-validation-prep  (only when backend tests run)
[STEP] backend-validation-run   (only when backend tests run)
[STEP] frontend-validation-plan
[STEP] frontend-deps-install    (only when frontend present)
[STEP] frontend-build           (only when frontend present)
[STEP] frontend-tsc             (when tsc is enabled)
[STEP] frontend-tests-run       (when frontend Vitest is enabled)
[STEP] restart-services
[STEP] health-checks
```

When a real deploy fails, look for the **last `[STEP]` line printed** —
that is the phase the script died in.

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

## Troubleshooting

### `SRC:` prints the parent folder when args are passed

**Symptom.** Running

```powershell
.\deploy-macmarket-trader.bat -TestProfile fast
```

prints

```
SRC: C:\Users\ryanm\OneDrive\Documents\GitHub
[ERROR] Source path does not look like the MacMarket repo: ...
```

instead of `SRC: C:\Users\ryanm\OneDrive\Documents\GitHub\MacMarket-Trader`.
Running with no args resolves SRC correctly.

**Root cause.** Plain `shift` in batch rotates `%0` in addition to
`%1+`. After several `shift` calls in the argument parser, `%~dp0` no
longer points at the script's own directory — it falls back to the
current working directory. A later `for %%I in ("%~dp0..") do set
"SRC=%%~fI"` then resolves to the parent of the cwd instead of the
parent of the script.

**Fix.** The wrapper resolves `REPO_ROOT` from `%~dp0` up-front and
`pushd`s into the repo root before invoking the canonical script. The
canonical script captures `SCRIPT_DIR=%~dp0` and `SRC` **before** any
arg parsing happens. Validate with:

```powershell
.\deploy-macmarket-trader.bat -TestProfile fast -DryRun
.\deploy-macmarket-trader.bat -TestProfile full -DryRun
.\deploy-macmarket-trader.bat -DryRun
```

Each of these must print

```
SRC: C:\Users\ryanm\OneDrive\Documents\GitHub\MacMarket-Trader
```

and exit 0 without mirroring / installing / building / restarting.

### `... was unexpected at this time.`

**Symptom.** The deploy mirrors files, installs backend dependencies,
applies schema updates, then fails with the literal message

```
... was unexpected at this time.
```

**Root cause.** Inside a parenthesized `IF` / `IF...ELSE` block, the
batch parser pre-scans the body for the matching `)`. Strings that
contain a literal `)` (for example `SKIPPED (emergency)`, `echo
[INFO] Running backend tests (profile: %TEST_PROFILE%)...`, or
`echo [INFO] Running TypeScript check (tsc --noEmit)...`) close the
block prematurely, so the subsequent block ends up unbalanced. Note:
`"..."` quoting does **not** protect parens here — quoted parens
inside an `IF` body still miscount.

**Fix.** Two waves of cleanup landed:

1. The arg parser and `[emergency]` / profile-description set lines
   were moved out of parenthesized IF blocks (replaced with goto
   handlers and single-line `if … set …` statements).
2. The post-schema backend / frontend validation paths were extracted
   into named subroutines (`:RUN_BACKEND_VALIDATION`, `:FRONTEND_PHASE`,
   `:INSTALL_FRONTEND_DEPS`, `:BUILD_FRONTEND`,
   `:RUN_TYPESCRIPT_CHECK`, `:RUN_FRONTEND_VALIDATION`,
   `:RUN_PLAYWRIGHT`) so the offending `echo … (profile: …)` and
   `echo … (tsc --noEmit)` lines no longer live inside a top-level
   parenthesized block. The remaining literal-paren echo (`echo
   Default profile is "full" (full backend pytest + …).`) lives inside
   the `:HANDLE_HELP` subroutine, reached only via `goto :HANDLE_HELP`,
   so it cannot collide with any outer block parser.

**How to confirm the fix on a given machine.** Run

```powershell
.\deploy-macmarket-trader.bat -TestProfile fast -ValidateRealPath
.\deploy-macmarket-trader.bat -TestProfile full -ValidateRealPath
.\deploy-macmarket-trader.bat -ValidateRealPath
```

Each must exit 0 and print

```
[STEP] backend-validation-plan
[STEP] frontend-validation-plan
[STEP] validate-real-path-exit
```

If any invocation surfaces `... was unexpected at this time.` the
parser-safety static test
(`tests/test_deploy_profiles.py::test_no_parens_inside_top_level_if_block_bodies`)
should also fail and identify the offending line.

### Source-path validation diagnostics

If `SRC` does not look like the MacMarket repo, the canonical script
now prints `SCRIPT_DIR`, `CWD`, the active `TEST_PROFILE`, and the
`DRY_RUN` flag alongside the failing `SRC` value. The four required
markers checked are:

- `README.md`
- `pyproject.toml`
- `apps\web`
- `src\macmarket_trader`

If any one is missing the script exits non-zero with the diagnostic
banner, regardless of the test profile.
