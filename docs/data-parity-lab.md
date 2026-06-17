# Market Data Parity Lab

The Market Data Parity Lab is an admin-only diagnostic surface for comparing
MacMarket's active or legacy market-data provider with Schwab/Thinkorswim
market data. It is read-only and exists to isolate whether
Thinkorswim/MacMarket differences come from raw provider bars, MacMarket
normalization/resampling, deterministic indicator math, or Thinkorswim
chart/study settings.

Schwab/Thinkorswim can now be the primary read-only market-data provider with
`MARKET_DATA_PROVIDER=schwab`. When Schwab is already primary, the lab compares
legacy Polygon/Massive to Schwab only if a legacy key is still configured.
Without a legacy provider, the lab reports that no useful comparison target is
configured instead of comparing Schwab to itself.

## What It Adds

- Schwab OAuth connection for read-only market data.
- Schwab quotes and historical OHLCV bars for `1W`, `1D`, `4H`, `1H`, and
  `30M` parity runs.
- Admin page at `/admin/data-parity`.
- Optional saved parity snapshots for audit/debug review.
- Manual Thinkorswim reference fields for values copied from TOS screenshots or
  studies.

It does not add Schwab order endpoints, broker routing, live trading, automatic
position close, recommendation scoring changes, replay changes, paper order
lifecycle changes, or hidden fallback behavior.

## Schwab Setup

Configure these variables server-side only:

```env
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
session policy, completed-bars-only comparison mode, snapshot saving, and
optional TOS manual references. Tolerances are kept in the backend defaults:
price absolute tolerance `0.01`, price relative tolerance `0.0005`, and volume
relative tolerance `1%`.

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
- full UTC and `America/New_York` latest-bar timestamps for each provider
- measured lag in minutes versus the server run time
- measured lag in minutes versus the expected latest regular-hours market bar
- timestamp-delta and latest-common aligned timestamp metadata
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
- timestamp convention diagnostics: `bar_start`, `bar_end`, `session_anchor`,
  or `unknown`
- canonical interval start/end and whether each latest bar is completed or
  still in progress at server run time

Intraday comparisons use MacMarket's regular-hours buckets in
`America/New_York`: `30M` buckets run from `09:30-16:00`, `1H` buckets run
`09:30-15:30` with the final `15:30-16:00` bucket, and `4H` buckets run
`09:30-13:30` and `13:30-16:00`. Weekly bars use the provider's weekly candle
frequency as the source anchor; the parity response exposes that source metadata
instead of implying a custom Thinkorswim weekly anchor.

Legacy Polygon/Massive weekly comparison requests ask for the newest weekly
aggregates first and then sort by canonical timestamp before returning the
latest requested window. The expanded metadata includes the redacted request
path/query, `from`/`to`, `sort`, `adjusted`, result count, pages followed, and
returned first/latest timestamps when a legacy provider is configured.

Daily and weekly parity alignment is diagnostic-normalized before comparing
OHLCV and indicator bundles:

- `1D` bars align by market session date, so provider-specific UTC anchors such
  as `04:00Z` versus `05:00Z` remain visible but do not force
  `no_aligned_bars`.
- `1W` bars align by canonical trading week (`Monday` through `Friday`), so a
  Polygon Sunday boundary and Schwab/TOS Monday boundary for the same covered
  week compare under one week label.
- Intraday `30M`, `1H`, and `4H` bars align by canonical covered interval
  when the provider timestamp convention shows equivalent bar-start/bar-end
  labels. For example, a Polygon/Massive `10:30` bar-start label and a Schwab
  `11:00` bar-end label can align to the same `10:30-11:00 ET` interval.
  Truly different intraday intervals remain not comparable.

The response preserves raw provider timestamps, the canonical session date or
week/interval label, the alignment mode used, inferred timestamp convention,
canonical interval start/end, completed/in-progress status, and an alignment
failure reason when bars remain not comparable. Indicator comparison uses
aligned canonical copies for `1D`, `1W`, and intraday interval labels so
timestamp-anchor differences alone do not create false indicator mismatches.
This is Data Parity Lab-only diagnostic behavior and does not alter production
recommendation inputs or math.

During regular market hours, the lab defaults to completed bars only. Current
in-progress intraday, daily, and weekly bars remain visible in the expanded
diagnostics as the latest provider-returned bars, but they are excluded from the
default verdict comparison until the operator opts into all returned bars. This
prevents partial current bars from being labeled as real provider or indicator
mismatches.

Layer 3 compares derived MacMarket indicator bundles using existing repo
functions only:

- True Momentum score/data
- HACO current state and latest flip
- HACOLT current direction
- Hi/Lo data
- Squeeze Pro state/histogram

If a component is not present or fails safely, the response marks that component
unavailable instead of inventing replacement math.

## Freshness and Delay

The lab measures freshness from provider timestamps only. It does not assume a
provider is delayed or real-time from documentation, subscription labels, or
account names.

Each row exposes:

- server run time in UTC and `America/New_York`
- detected market session state: `premarket`, `regular`, `after-hours`, or
  `closed`
- expected latest regular-hours market bar for the requested/source timeframe
- latest current-provider bar timestamp
- latest Schwab bar timestamp
- latest common aligned timestamp used for canonical/indicator comparison
- latest returned provider timestamp versus latest compared completed timestamp
- canonical interval start/end for the latest compared row
- inferred provider timestamp convention
- provider lag in minutes versus the server run time
- provider lag in minutes versus the expected latest market bar
- timestamp delta between current-provider and Schwab latest bars
- freshness classification: `real_time_like`, `delayed_15_min_like`, `stale`,
  or `not_comparable`

The delay classification is intentionally measured, not assumed. During the
regular session, a latest provider bar around 15 minutes behind the expected
latest market bar is labeled `delayed_15_min_like`; a bar within tolerance is
`real_time_like`; and timestamps outside tolerance are labeled `stale` or
`not_comparable`. The session model is a regular-hours weekday diagnostic model
for U.S. equities and ETFs; it does not replace a full exchange holiday
calendar.

Provider-returned bars are sorted by canonical timestamp before latest/as-of
and lag calculations are made, so freshness diagnostics do not depend on the
HTTP adapter's response ordering. The UI and CSV export both include UTC and
`America/New_York` timestamps, provider lag versus server run time, provider
lag versus expected latest market bar, timestamp delta, aligned latest
timestamp, classification, and verdict reason.

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

The lab separates "not comparable yet" from true mismatch states. Indicator
bundles are compared only after canonical bars match on aligned timestamps,
session dates, trading weeks, or intraday interval keys. If providers are not
aligned to the same canonical comparison key, indicator comparison is skipped
rather than labeled as an indicator mismatch.

- `provider_unavailable`: a provider, entitlement, parsing, or validation error
  prevented comparison.
- `auth_unavailable`: Schwab OAuth/config/token state is not usable for the
  diagnostic pull.
- `no_bars`: at least one side returned no bars.
- `insufficient_data`: aligned bars exist but there are too few to compare
  safely.
- `stale_source`: provider latest timestamps differ beyond timeframe tolerance.
- `no_aligned_bars`: both sides returned bars, but there are no common
  timestamp/session/week/interval alignment keys.
- `comparable_raw_mismatch`: aligned raw provider bars differ materially.
- `comparable_normalized_mismatch`: raw bars are usable, but canonical
  MacMarket bars differ after normalization/resampling.
- `comparable_indicator_mismatch`: canonical bars match, but deterministic
  MacMarket indicator output differs on the latest common aligned series.
- `tos_reference_mismatch`: MacMarket current/Schwab indicator paths agree but
  manual TOS values differ.
- `match`: available comparable layers match within tolerance.

## Testing Workflow

1. Connect Schwab from Admin -> Data Parity Lab.
2. If Schwab is primary and no legacy key is configured, confirm the lab reports
   `schwab_primary_no_legacy`.
3. If a legacy Polygon/Massive key is configured for cutover validation, run
   `SPY`, `QQQ`, and `MTUM` across `1W`, `1D`, `4H`, `1H`, and `30M`.
4. Review raw provider bars first.
5. Review canonical bars after MacMarket normalization/resampling.
6. Enter manual TOS reference values from a screenshot or TOS study readout.
7. Use the root-cause verdict and expanded row details to classify the mismatch.

Saved snapshots are optional and contain request/response diagnostics only. They
must not contain Schwab tokens, client secrets, authorization headers, or broker
execution data.
