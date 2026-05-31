# Market Data Parity Lab

The Market Data Parity Lab is an admin-only diagnostic surface for comparing
MacMarket's current market-data provider with Schwab Trader API market data.
It is read-only and exists to isolate whether Thinkorswim/MacMarket differences
come from raw provider bars, MacMarket normalization/resampling, deterministic
indicator math, or Thinkorswim chart/study settings.

## What It Adds

- Schwab OAuth connection for diagnostic market data only.
- Schwab quotes and historical OHLCV bars for `1W`, `1D`, `4H`, `1H`, and
  `30M` parity runs.
- Admin page at `/admin/data-parity`.
- Optional saved parity snapshots for audit/debug review.
- Manual Thinkorswim reference fields for values copied from TOS screenshots or
  studies.

It does not add Schwab order endpoints, broker routing, live trading, automatic
position close, recommendation scoring changes, replay changes, paper order
lifecycle changes, or a primary-provider default change.

## Schwab Setup

Configure these variables server-side only:

```env
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
```

`SCHWAB_TOKEN_ENCRYPTION_KEY` must be a Fernet key, for example:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never put Schwab client secrets, access tokens, refresh tokens, or authorization
headers in frontend code, browser-visible JSON, docs, logs, screenshots, or test
snapshots.

## Data Parity Settings

```env
DATA_PARITY_ENABLED=true
DATA_PARITY_DEFAULT_LOOKBACK_BARS=250
DATA_PARITY_MAX_LOOKBACK_BARS=500
DATA_PARITY_MAX_SYMBOLS=10
DATA_PARITY_SAVE_SNAPSHOTS=true
```

The first-pass UI exposes symbols, timeframes, lookback bars, regular-hours
session policy, snapshot saving, and optional TOS manual references. Tolerances
are kept in the backend defaults: price absolute tolerance `0.01`, price
relative tolerance `0.0005`, and volume relative tolerance `1%`.

## Callback URL

Register this callback in the Schwab developer app:

```text
https://api.macmarket.io/auth/schwab/callback
```

Local or staging deployments should use the matching backend callback URL for
that environment. The callback validates a server-stored OAuth state and does
not require Clerk auth because Schwab redirects directly to it.

## Diagnostic Layers

Layer 1 compares raw provider bars:

- bar counts
- first/latest timestamps
- latest OHLCV
- maximum OHLC delta on aligned timestamps
- maximum volume delta
- missing/extra timestamps
- latest timestamp match

Layer 2 compares canonical MacMarket bars after regular-hours normalization and
intraday resampling:

- the same raw-bar metrics
- session policy metadata
- source timeframe metadata
- weekly-provider anchoring metadata for `1W`
- regular-hours bucket boundaries for intraday `30M`, `1H`, and `4H`

Intraday comparisons use MacMarket's regular-hours buckets in
`America/New_York`: `30M` buckets run from `09:30-16:00`, `1H` buckets run
`09:30-15:30` with the final `15:30-16:00` bucket, and `4H` buckets run
`09:30-13:30` and `13:30-16:00`. Weekly bars use the provider's weekly candle
frequency as the source anchor; the parity response exposes that source metadata
instead of implying a custom Thinkorswim weekly anchor.

Layer 3 compares derived MacMarket indicator bundles using existing repo
functions only:

- True Momentum score/data
- HACO current state and latest flip
- HACOLT current direction
- Hi/Lo data
- Squeeze Pro state/histogram

If a component is not present or fails safely, the response marks that component
unavailable instead of inventing replacement math.

## Thinkorswim References

Schwab market-data APIs provide market data, not custom Thinkorswim study output.
The parity lab therefore cannot pull TOS custom values directly. Enter TOS
reference values manually from a screenshot or study readout when you want to
compare:

- current provider -> MacMarket indicators
- Schwab provider -> MacMarket indicators
- manually entered TOS reference values

Manual TOS references can classify a run as `tos_reference_mismatch` when both
MacMarket-derived indicator paths agree with each other but differ from the
entered TOS value.

## Root-Cause Verdicts

- `schwab_not_connected`: Schwab OAuth/config is missing, expired, or needs
  reconnect.
- `raw_provider_mismatch`: current-provider raw bars differ materially from
  Schwab raw bars.
- `normalization_mismatch`: raw bars broadly match but canonical MacMarket bars
  differ after normalization/resampling.
- `indicator_mismatch`: canonical bars match but deterministic indicator output
  differs.
- `tos_reference_mismatch`: MacMarket current/Schwab indicator paths agree but
  manual TOS values differ.
- `match`: available layers match within tolerance.
- `insufficient_data`: too few aligned bars are available.
- `error`: a provider, entitlement, parsing, or validation error occurred.

## Testing Workflow

1. Connect Schwab from Admin -> Data Parity Lab.
2. Run `SPY`, `QQQ`, and `MTUM` across `1W`, `1D`, `4H`, `1H`, and `30M`.
3. Review raw provider bars first.
4. Review canonical bars after MacMarket normalization/resampling.
5. Enter manual TOS reference values from a screenshot or TOS study readout.
6. Use the root-cause verdict and expanded row details to classify the mismatch.

Saved snapshots are optional and contain request/response diagnostics only. They
must not contain Schwab tokens, client secrets, authorization headers, or broker
execution data.
