# Chart history ranges

Every chart rendered in the operator console now supports an explicit
**history range** selector. Picking a wider range asks the backend for
more historical bars so the operator can pan the chart farther back in
time without losing the existing zoom / pan behavior.

The selector is research-only context. It does **not** affect ranking
math, recommendation queue sorting, recommendation approval, paper-order
creation, replay behavior, options preview, Momentum indicator math, or
Phase C strategy-family preview behavior.

## Supported ranges

| Id | Label | Lookback days | Note |
|---|---|---:|---|
| `1M` | 1M | 31 | ~1 month of bars |
| `3M` | 3M | 93 | ~3 months of bars |
| `6M` | 6M | 186 | ~6 months of bars |
| `1Y` | 1Y | 366 | **default** for every chart surface |
| `2Y` | 2Y | 732 | ~2 years of bars |
| `5Y` | 5Y | 1830 | ~5 years of bars |

Frontend constants: `apps/web/lib/chart-history-range.ts`.
Backend constants: `CHART_HISTORY_RANGE_LOOKBACK_DAYS` in
`src/macmarket_trader/domain/schemas.py`.

## Surfaces

The selector is mounted on every chart surface in the app:

- Momentum Intelligence workspace (`/charts/momentum`).
- HACO workspace.
- Recommendation detail chart context (HACO + Momentum together).
- Analysis (Strategy Workbench) chart.
- Analyze (triage) page Momentum context (uses the persisted range
  without an inline selector).

Each callsite uses the same shared component
(`apps/web/components/charts/chart-history-range-select.tsx`) and the
same persisted preference key.

## API surface

Chart endpoints accept the range as a request body field. Unknown
values fall back to `1Y` so a malformed payload never breaks a chart.

```http
POST /charts/momentum
POST /charts/haco
{
  "symbol": "AAPL",
  "timeframe": "1D",
  "history_range": "5Y"
}
```

Both endpoints echo the resolved range plus diagnostic metadata on the
response:

| Field | Meaning |
|---|---|
| `history_range` | Resolved allowlisted id (`1M` / `3M` / `6M` / `1Y` / `2Y` / `5Y`). |
| `lookback_days` | Resolved day count (31 / 93 / 186 / 366 / 732 / 1830). |
| `bars_returned` | Number of bars in the response payload (after provider/fallback resolution). |

The provider bar-fetch limit is derived per-timeframe from the
selected range:

- `1D`: `max(lookback_days, 60)` bars.
- `1H`: `min(max(lookback_days * 7, 400), 4000)` bars.
- `4H`: `min(max(lookback_days * 2, 200), 2000)` bars.

Intraday limits are deliberately capped to keep provider calls bounded
even when the operator selects `5Y`.

## Persistence

The selected range is persisted in `localStorage` under
`macmarket.chart.historyRange`. Every chart surface reads the same key
on mount and writes back on change, so flipping the selector in one
place propagates to the next chart surface the operator opens. Invalid
or corrupted entries fall back to `1Y`.

## What this never changes

- Ranking math. `DeterministicRankingEngine` and
  `build_momentum_ranking_contribution` are byte-identical.
- Recommendation queue sorting.
- Recommendation approval, promote, save, paper-order, settle, replay,
  or options-preview behavior.
- Momentum indicator math.
- Phase C True Momentum strategy preview / evidence behavior.

The chart range is purely display / research context: the operator can
now look at more bars without affecting any decision-making code path.
