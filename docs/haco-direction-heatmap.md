# HACO Direction Heatmap

The HACO Direction Heatmap is a research dashboard for scanning HACO
directional state across multi-symbol workbook-style universes. It reuses the
existing HACO chart implementation and stores its profile, snapshot, and report
history separately from Momentum Heatmap.

It does not create recommendations, approve trades, size positions, route
orders, or add live-trading or execution behavior.

## Purpose

`/haco-heatmap` gives operators a dense LONG / SHORT directional read across
the same practical universes used by Momentum Heatmap:

- Morning Macro
- Growth Leaders
- Commodities
- Pullback Watch
- Custom Watchlist

The page is HACO state based. It is not a True Momentum strength dashboard and
does not use the Momentum Heatmap `-100` to `100` score formulas.

## Timeframes

The HACO Direction Heatmap uses the shared chart timeframe set:

- `1W`
- `1D`
- `4H`
- `1H`
- `30M`

Each cell returns the latest HACO direction for that symbol/timeframe:

- `LONG`
- `SHORT`
- `UNAVAILABLE` / unsupported, when a symbol or bar set cannot provide a HACO
  state

Overall and short-term bias may be `MIXED` when available timeframes conflict.
User-facing direction labels intentionally use LONG/SHORT/MIXED/UNAVAILABLE,
not BUY/SELL.

## State model

For alignment math only:

- LONG = `+1`
- SHORT = `-1`
- unavailable/unsupported = excluded from the denominator

Overall HACO Alignment uses longer-term weighting:

`(1W*3 + 1D*3 + 4H*2 + 1H + 30M) / available_weight * 100`

Short-Term Alignment uses:

`(4H*2 + 1H + 30M) / available_weight * 100`

Bias labels:

- `>= 60`: LONG
- `<= -60`: SHORT
- otherwise: MIXED

Daily Context is the `1D` state. Macro Context is the `1W` state.

These are research direction labels only.

## Tags

Current Phase 1 tags:

- All LONG
- All SHORT
- Daily LONG / Short-Term Pullback
- Daily SHORT / Short-Term Bounce
- Mixed / Chop
- Unsupported
- Fresh LONG Flip, when a later snapshot changes from SHORT/MIXED/unavailable
  to LONG
- Fresh SHORT Flip, when a later snapshot changes from LONG/MIXED/unavailable
  to SHORT

Fresh flip tags require a previous successful snapshot for the same HACO
profile/view.

## Profiles and account scoping

HACO Direction Heatmap profiles are stored in `haco_heatmap_profiles` and are
scoped by `app_user_id`. Each approved user receives independent seeded copies
of the saved views. Editing rows or include/collapse state in one account does
not mutate another account's HACO profile.

The HACO heatmap intentionally uses separate tables from Momentum Heatmap:

- `haco_heatmap_profiles`
- `haco_heatmap_snapshots`

This keeps HACO state history from polluting Momentum Heatmap scoring history.

## Refresh behavior

The frontend refreshes one included category at a time and chunks large row
sets. The backend also enforces one-category request work units, row caps,
request time-budget protection, and unsupported-symbol fast failure.

Unsupported workbook labels such as futures-style symbols, composite labels,
currency pairs, dollar-index labels, and FRED-style labels remain visible but
return unsupported/unavailable status instead of blocking the whole page.

The page does not auto-refresh on load. It loads the latest snapshot when one
exists and waits for the operator to refresh.

## Snapshots and changes

HACO snapshots store:

- selected profile/view
- requested categories and rows
- per-timeframe HACO states, status, reason, source, fallback flag, and as-of
- overall and short-term alignment calculations
- category summaries
- unsupported/unavailable summary
- previous snapshot linkage when available

Changes compare the current snapshot with the previous successful snapshot for
the same profile/view. If only one snapshot exists, the UI shows:

`Changes need two successful snapshots.`

## Report and CSV

The backend report generator produces preview HTML and CSV for the selected
HACO profile/snapshot.

Report sections include:

1. Generated timestamp
2. Data-as-of note
3. Research-only disclaimer
4. Category direction summary
5. Category LONG/SHORT breadth
6. All LONG rows
7. All SHORT rows
8. Fresh LONG flips when snapshot history exists
9. Fresh SHORT flips when snapshot history exists
10. Daily LONG / Short-Term Pullback rows
11. Daily SHORT / Short-Term Bounce rows
12. Mixed / Chop rows
13. Unsupported/unavailable summary
14. Full table

HACO Direction Heatmap scheduled email delivery is available through the shared
Scheduled Reports system with `report_type=haco_heatmap`. The schedule stores a
static symbol snapshot, selected heatmap timeframes, and sends to the signed-in
account email. It reuses the existing email provider boundary and
`strategy_report_runs` audit table.

The scheduled email is research-only. It does not create recommendations,
paper orders, broker orders, approval events, sizing decisions, or live-trading
actions.

Run all due scheduled reports, including HACO heatmaps, with:

```bash
python -m macmarket_trader.cli run-due-strategy-schedules
```

## Limitations

- Phase 1 uses JSON profile payloads rather than normalized row/cell tables.
- HACO scheduled delivery is configured from `/schedules` rather than from a
  dedicated HACO Heatmap schedule-preferences panel.
- Unsupported symbols remain in seeded universes but fail fast where the
  current market data provider does not support them.
- HACO is a directional state model, not a Momentum Intelligence score.
- No live-trading, broker-routing, automated execution, order-placement, or
  recommendation approval behavior is added.
