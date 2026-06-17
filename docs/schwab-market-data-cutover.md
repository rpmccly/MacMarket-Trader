# Schwab Market-Data Cutover

Last updated: 2026-06-17

## What Changed

- `MARKET_DATA_PROVIDER=schwab` now selects `SchwabMarketDataProvider` as the
  active read-only market-data provider.
- Explicit provider selection is deterministic: `POLYGON_ENABLED=true` no
  longer overrides `MARKET_DATA_PROVIDER=schwab`.
- Schwab now implements the production market-data contract where the API and
  account entitlements allow it: historical bars, latest equity snapshots,
  index snapshots, option contract listing/resolution, option mark snapshots,
  and provider health.
- Provider-backed workflow reads block with an explicit unavailable/error state
  when Schwab is degraded and demo fallback is not allowed.
- Provider Health and Data Parity Lab now label Schwab/Thinkorswim as the
  selected provider and surface OAuth, entitlement, index, options, latency, and
  workflow mode signals.
- Data Parity Lab compares legacy Polygon/Massive to Schwab only when a legacy
  key is configured. Otherwise it reports that Schwab is already primary and no
  useful legacy comparison source exists.

No Schwab broker execution, live trading, order routing, assignment/exercise
automation, recommendation scoring, sizing, paper OMS, replay semantics, or LLM
behavior was added or intentionally changed.

## Remaining Legacy Polygon/Massive Code

- `PolygonMarketDataProvider` remains available as a legacy rollback/comparison
  provider.
- Polygon/Massive news context remains a separate news-provider integration when
  configured; it is not required for Schwab-backed equity market-data reads.
- Data Parity Lab may use a configured legacy `POLYGON_API_KEY` to compare
  Polygon/Massive bars against Schwab during cutover validation.
- Existing Polygon tests remain as legacy coverage and should not require a
  production Polygon key.

## Schwab Gaps and Explicit Blocks

- Schwab index and options support depends on API/account entitlements. Missing
  or unentitled SPX/NDX/RUT/VIX/DJI/COMP or options reads must surface as
  unavailable, degraded, or not-entitled health states.
- Latest equity snapshots use complete Schwab quote OHLCV where available;
  otherwise they use the normalized latest historical bar. Quote-only data is
  not expanded into fabricated OHLCV.
- Option marks prefer bid/ask midpoint, then provider mark, then last trade.
  Previous-close/stale fallback is labeled explicitly and no option marks are
  fabricated.
- Production workflows must not silently use deterministic fallback when Schwab
  is unavailable and `WORKFLOW_DEMO_FALLBACK=false`.

## Required Production Env

```bash
MARKET_DATA_PROVIDER=schwab
MARKET_DATA_ENABLED=true
SCHWAB_ENABLED=true

SCHWAB_CLIENT_ID=
SCHWAB_CLIENT_SECRET=
SCHWAB_REDIRECT_URI=https://api.macmarket.io/auth/schwab/callback
SCHWAB_BASE_URL=https://api.schwabapi.com
SCHWAB_AUTH_URL=https://api.schwabapi.com/v1/oauth/authorize
SCHWAB_TOKEN_URL=https://api.schwabapi.com/v1/oauth/token
SCHWAB_MARKET_DATA_BASE_URL=https://api.schwabapi.com/marketdata/v1
SCHWAB_REQUEST_TIMEOUT_SECONDS=8
SCHWAB_ACCESS_TOKEN_REFRESH_LEEWAY_SECONDS=90
SCHWAB_TOKEN_ENCRYPTION_KEY=

POLYGON_ENABLED=false
POLYGON_API_KEY=
```

Keep Schwab secrets and tokens server-side only. Never commit tokens, client
secrets, token encryption keys, authorization headers, or saved parity snapshots
containing secrets.

## Validation Commands

```bash
pytest tests/test_schwab_market_data_provider.py tests/test_market_data_service.py tests/test_data_parity_service.py tests/test_data_parity_api.py

cd apps/web
npm test
npx tsc --noEmit
npm run build
```

## Manual Checks Before Canceling Massive

- Start the backend with the required Schwab env and no Polygon key.
- Connect Schwab OAuth from Admin -> Data Parity Lab.
- Open `/admin/provider-health` and confirm configured provider, effective read
  mode, and workflow execution mode are Schwab/provider rather than fallback.
- Confirm Schwab OAuth connected, token status, index readiness, options
  readiness, and sample latency are visible and sanitized.
- Open Dashboard, Strategy Workbench/Analysis, Recommendations chart context,
  Replay, Orders, HACO Context, and Momentum workflows and confirm source chips
  show Schwab or a clearly labeled blocked/unavailable state.
- Run Data Parity Lab. If no legacy Polygon/Massive key is configured, confirm
  it says Schwab is already primary and no legacy comparison provider exists.
- If keeping a temporary legacy key, run representative `1W`, `1D`, `4H`, `1H`,
  and `30M` comparisons before removing the key.
