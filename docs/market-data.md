# Market Data Setup (Schwab/Thinkorswim Primary)

MacMarket-Trader v1 now treats **Schwab/Thinkorswim** as the primary read-only
market-data provider. Polygon/Massive remains a legacy rollback or optional
cutover-comparison provider only.

Schwab market data does not add Schwab broker execution, live trading, order
routing, assignment/exercise automation, or any change to recommendation,
sizing, replay, paper OMS, or LLM behavior beyond normal reads through the
market-data provider abstraction.

## Backend `.env` variables (repo root)

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

Generate `SCHWAB_TOKEN_ENCRYPTION_KEY` with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

After setting server-side Schwab credentials, connect OAuth from
Admin -> Data Parity Lab. Schwab access and refresh tokens remain encrypted and
server-side only.

## Supported Schwab Reads

- Equity historical bars for `1W`, `1D`, `4H`, `1H`, and `30M`.
- Regular-hours-only equity bars using the New York market timezone.
- Intraday normalization from Schwab 30-minute bar-end labels into MacMarket
  RTH buckets for `30M`, `1H`, and `4H`.
- Latest equity snapshots from complete Schwab quote OHLCV when available,
  otherwise the normalized latest historical bar.
- Index snapshots through mapped Schwab/TOS symbols for `SPX`, `NDX`, `RUT`,
  `VIX`, `DJI`, and `COMP` when the account is entitled.
- Options research chain, contract resolution, and mark snapshots when the
  Schwab account is entitled.

Unsupported or unentitled Schwab features must report explicit unavailable,
blocked, or warning states. The app must not silently fall back to
Polygon/Massive or deterministic demo data in production workflows.

## Fallback Behavior

Fallback mode is explicit. It is used when:

- `MARKET_DATA_PROVIDER=fallback`, or
- provider-backed market data is disabled, or
- `WORKFLOW_DEMO_FALLBACK=true` in `dev`, `local`, or `test` and the selected
  provider is degraded.

When provider-backed market data is configured and degraded:

- With `WORKFLOW_DEMO_FALLBACK=false`, user-facing workflows are blocked.
- With `WORKFLOW_DEMO_FALLBACK=true` in `dev/local/test`, workflows may use
  deterministic demo bars and must label that source clearly.

## Legacy Polygon/Massive

Keep this disabled for Schwab-first production:

```bash
POLYGON_ENABLED=false
POLYGON_API_KEY=
```

If a legacy Polygon/Massive key is still configured, the Market Data Parity Lab
can use it as an optional legacy-vs-Schwab comparison source during cutover
validation. It should not be required for Dashboard, charts, HACO/momentum
workflows, Recommendations, Replay, risk/index checks, or provider health.

## UI Indicators

- Dashboard provider summary shows configured provider, effective read mode,
  workflow execution mode, and failure reason.
- Provider Health shows Schwab/Thinkorswim OAuth, entitlement, sample latency,
  index readiness, options readiness, and last successful fetch.
- Strategy Workbench, Recommendations, Replay, Orders, HACO Context, and
  related charts must label provider-backed versus fallback data consistently.

## Alternate Scaffold

Alpaca market data remains an alternate scaffold:

```bash
MARKET_DATA_PROVIDER=alpaca
MARKET_DATA_ENABLED=true
APCA_API_KEY_ID=
APCA_API_SECRET_KEY=
ALPACA_MARKET_DATA_BASE_URL=https://data.alpaca.markets
ALPACA_MARKET_DATA_FEED=iex
```

Alpaca paper-provider readiness remains separate from market-data provider
selection and does not enable live brokerage execution.
