# Momentum Heatmap Profiles, Snapshots, and Reports

The Momentum Heatmap is a research dashboard built on the existing Momentum
Intelligence / True Momentum score path. It does not create trade
recommendations, approve trades, size positions, route orders, or add execution
support.

HACO Direction Heatmap is documented separately in
`docs/haco-direction-heatmap.md`. It uses the existing HACO chart path and
separate HACO profile/snapshot tables so directional LONG/SHORT state history
does not mix with Momentum Heatmap scoring history.

## Operator dashboard polish

The Momentum Heatmap page now uses a compact command-center layout instead of
stacked full-width controls. The top area shows the active server profile, last
snapshot/refresh context, and the current refresh/report status. Primary
actions stay near the table workflow:

- Refresh visible heatmap
- Generate report preview
- Download CSV
- Manage symbols
- Score color ranges
- Report settings
- Schedule settings

Manage-symbol, color-range, report, and schedule controls are collapsed by
default. Sorting and filtering sit directly above the category tables, and each
category header includes include/exclude state, category status, average
strength, compact summary counts, a per-category refresh button, and collapse
control. Refresh progress shows the current category plus completed
categories/rows while preserving partial/prior results.

## Server-side profile model

Momentum Heatmap profiles are user-scoped rows in
`momentum_heatmap_profiles`.

Stored profile fields include:

- profile id (`profile_uid`)
- owning app user id
- profile name, default active seeded view `Morning Macro`
- description, slug, view type, and system-seeded/custom metadata stored in
  profile view settings
- workbook-derived categories and rows
- include/exclude and collapsed category state
- row display label, provider symbol, original/workbook symbol, workbook order,
  enabled state, user-added state, unsupported/deferred hints, and notes
- score color range settings
- default sort/filter/delta display settings
- report preference defaults
- created and updated timestamps

The current implementation uses JSON profile payloads for categories and rows
so the workbook-style structure can evolve without prematurely normalizing
every cell. Duplicate prevention is deterministic: provider symbols are trimmed
and uppercased, duplicates in the same category are blocked, and duplicates in
another category are allowed with a warning.

## Saved heatmap views

On first Momentum Heatmap setup, each approved user receives independent
server-owned saved views. They are not global mutable profiles:

- **Morning Macro**: broad morning market regime read using INDEXES, SECTORS,
  BONDS + MISC, and COMMODITIES workbook categories.
- **Growth Leaders**: growth, high-beta, and leadership scan using selected
  index, sector, and major-stock rows such as QQQ, SMH, XLK, NVDA, MSFT,
  META, TSLA, and related leadership names.
- **Commodities**: commodity/rates/inflation-sensitive scan using the
  COMMODITIES workbook category plus related dollar, rates, energy, metals,
  and miner tickers. Unsupported futures, dollar-index, and FRED-style rows
  remain visible and fail fast where provider support is unavailable.
- **Pullback Watch**: research-candidate view for long-term bullish rows where
  shorter-term momentum is weaker or cooling. Its default filters hide
  unsupported rows and favor long-term bullish plus short-term weak context.
- **Custom Watchlist**: lightly seeded SPY, QQQ, IWM, NVDA, and TSLA view
  intended as the easiest user-editable watchlist.

The UI exposes an active view selector plus create, rename, duplicate, reset
seeded view, and delete custom view actions. Seeded views are protected from
deletion; custom duplicated/created views are user-owned and can be removed.
Switching views loads that view's rows, settings, schedule preferences, and
latest snapshot without auto-refreshing.

The frontend still reads the legacy localStorage keys once:

- `macmarket-momentum-heatmap-symbols-v1`
- `macmarket-momentum-heatmap-colors-v1`

Legacy browser customizations are not automatically imported into a server
profile on page load, which prevents one shared browser from overwriting a
different account's saved Heatmap views. If the server profile cannot load,
localStorage is used only as an emergency fallback with a visible warning.

## Snapshot behavior

Momentum Heatmap refreshes now use:

- frontend category/row chunks
- backend one-category work units
- backend row and time-budget protection
- unsupported-symbol fast rejection before provider calls where possible
- partial result preservation

`POST /user/momentum-heatmap/refresh` produces the same heatmap scores as the
chart heatmap path and stores a snapshot in `momentum_heatmap_snapshots` for
the selected profile/view when a non-empty chunk completes. Snapshot rows
preserve:

- per-cell score, status, reason, data source, fallback flag, and `as_of`
- Long-Term Score
- Short-Term Score
- Strength %
- Squeeze Pro state summary and per-timeframe Squeeze Pro details when
  available
- category summaries
- unsupported/unavailable summary
- previous snapshot linkage where available

Empty refresh requests are rejected rather than stored as broken empty
snapshots.

## Stale-data behavior

On page load, the frontend loads the latest server snapshot if one exists and
shows:

`Loaded last snapshot from {timestamp}; refresh to update.`

The page does not auto-refresh. If a later chunk refresh fails for a row/cell
but a prior value exists, the UI preserves the prior value and marks it stale
instead of silently mixing old and fresh data. Category status is surfaced as
`fresh`, `partial`, `stale`, `not refreshed`, or `failed` depending on the
stored snapshot and latest refresh state. The default stale threshold is 24
hours and is stored with the profile view settings for future enforcement.

## Delta definitions

Deltas compare the current stored snapshot with the previous successful
snapshot for the same profile/view.

Current delta fields:

- Delta Strength %
- Delta Long-Term Score
- Delta Short-Term Score
- optional per-timeframe deltas for `1W`, `1D`, `4H`, `1H`, and `30M`
- became available
- became unavailable

Deltas are only numeric when both current and prior values are numeric. Missing,
unsupported, failed, or stale-only values do not receive fabricated deltas.
If only one successful snapshot exists, the UI shows `Deltas need two
successful snapshots.` New rows show `new` rather than a fabricated numeric
change, and rows with stale current values show an unavailable delta reason.

## Category summaries and row tags

Category summaries include:

- average Strength %
- average Long-Term Score
- average Short-Term Score
- count ok
- count unsupported
- count unavailable/error
- count bullish aligned
- count bearish aligned
- count improving
- count weakening

Row tags are research labels only:

- Trend leader
- Pullback in uptrend
- Short-term acceleration
- Possible reversal
- Bearish alignment
- Mixed/chop
- Unsupported
- Stale

These labels are not trade recommendations.

## Report sections

The backend report generator consumes the selected stored profile/view and
snapshot payload and produces preview HTML plus CSV data. It includes:

1. Generated timestamp
2. Data-as-of note
3. Stale-data disclaimer when applicable
4. Category average strength table
5. Top strongest rows by Strength %
6. Bottom weakest rows by Strength %
7. Biggest positive deltas
8. Biggest negative deltas
9. Bullish alignment rows
10. Bearish alignment rows
11. Long-term bullish plus short-term weak rows
12. Long-term weak plus short-term improving rows
13. Unsupported/unavailable summary
14. Full heatmap table
15. Notes:
    - Intraday timeframe scores use latest completed regular-hours bars.
    - Squeeze Pro is a research indicator and is not an execution signal.

CSV export includes category, display label, provider symbol, all workbook
score columns, deltas, squeeze status, row tags, statuses/reasons, and as-of
timestamps.

Report preview, print HTML, and email HTML now use the same branded inline-CSS
template so they do not depend on app global CSS. The template includes a
MacMarket research header, generated timestamp, data-as-of note, category
summary table, strongest/weakest rows, positive/negative movers, alignment
sections, pullback/reversal research sections, unsupported/unavailable summary,
and the full heatmap table with score colors and delta badges. Email also
includes a plain text research summary fallback through the existing email
provider boundary.

## Squeeze Pro integration

The heatmap now replaces the former deferred squeeze placeholder with
MacMarket Squeeze Pro research states where provider bars are available.
Squeeze Pro is computed separately from True Momentum and does not change:

- Long-Term Score
- Short-Term Score
- Strength %
- Momentum Intelligence parity
- recommendation approval, sizing, paper-order, or execution behavior

For each row/timeframe, the backend computes the latest Squeeze Pro state:

- High squeeze
- Mid squeeze
- Low squeeze
- No squeeze
- Unavailable

The displayed Squeezes column summarizes the strongest active state across the
requested timeframes and preserves per-timeframe details for tooltips, CSV, and
report rendering. Unsupported workbook labels still fail fast and show
unavailable Squeeze Pro state with a reason.

The report HTML, CSV, and email text include Squeeze Pro state when available.
They label it as research context only.

## Email behavior

MacMarket already has an email provider boundary and delivery logs. The
Momentum Heatmap report endpoint uses that existing boundary for explicit
operator-triggered report emails when recipients are supplied.

There is no live-trading, broker-routing, or execution content in the email
payload. Scheduled Momentum Heatmap delivery now runs through the shared
Scheduled Reports system with `report_type=momentum_heatmap`; it still requires
the operator to install the CLI runner through cron, Windows Task Scheduler, or
another approved worker.

## Schedule behavior

Momentum Heatmap page preferences are still persisted in
`momentum_heatmap_schedule_preferences` for the heatmap workspace itself.
Recurring email delivery is configured from `/schedules`, where a schedule
stores a static symbol snapshot and `report_type=momentum_heatmap` in
`strategy_report_schedules`.

Stored settings include:

- enabled true/false
- timezone, default `America/Indiana/Indianapolis`
- run time
- days of week
- report mode: latest snapshot or refresh then report
- included profile/view
- recipients
- include CSV attachment
- include full table

For scheduled report delivery, `/schedules` uses the saved schedule symbols,
selected heatmap timeframes, and the signed-in account email as the recipient.
It does not use strategy-scan ranking fields, does not create recommendation
queue candidates, and does not create paper/broker/live orders.

The UI shows helper suggestions:

- 7:00 AM ET: premarket read using prior completed session/intraday bars
- 10:15 AM ET: after market has enough regular-session data for 30M/1H context
- 3:30 PM ET: late-session review before close
- 4:30 PM ET: post-close summary

Run all due scheduled reports, including Momentum Heatmap schedules, with:

```bash
python -m macmarket_trader.cli run-due-strategy-schedules
```

The legacy Momentum-only runner remains available for targeted operational
checks:

```bash
python -m macmarket_trader.cli run-due-momentum-heatmap-reports
```

## Implemented vs deferred

Implemented:

- server-backed saved view seeding for Morning Macro, Growth Leaders,
  Commodities, Pullback Watch, and Custom Watchlist
- profile update/reset
- create, rename, duplicate, seeded-view reset, and custom-view delete
- add/remove row server-side
- duplicate prevention and cross-category warnings
- refresh snapshots
- latest snapshot load
- deltas
- category summaries
- row tags
- report preview
- CSV export
- explicit email-now path through the existing email provider boundary
- persisted schedule preferences
- scheduled email delivery through `/schedules` and `strategy_report_runs`
- localStorage migration/fallback

Deferred:

- user-editable stale threshold enforcement beyond stored profile settings
- provider support mapping for composite, futures, `$` index, currency-pair,
  and FRED-style workbook labels

Unsupported rows remain in the default universe intentionally and fail fast
with clear unsupported/unavailable reasons.

## Playwright coverage

The frontend E2E suite includes `tests/e2e/momentum-heatmap.spec.ts`. It mocks
same-origin heatmap APIs and covers:

- page load with server profile and latest snapshot banner
- no refresh request on initial load
- manage-symbol panel and duplicate same-category blocking
- chunked refresh start and visible progress
- category table rendering with unsupported rows labeled
- sorting/filter controls
- the one-snapshot delta empty-state message
- report preview, CSV control, color/schedule panel toggles
- email recipient authorization failure handling

The test is non-execution research UI coverage only; it does not call providers
or create recommendation, order, paper-order, broker-routing, or live-trading
behavior.
